"""
NEPSE AI Trading Bot — Flask Backend
======================================
API server that connects NEPSE data, Kronos AI predictions,
technical indicators, and the premium dashboard UI.
"""

import os
import sys
import json
import logging
import traceback
import numpy as np
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

# Setup paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
sys.path.insert(0, PROJECT_ROOT)

# Import our modules
from nepse_bot.nepse_data import NepseDataFetcher
from nepse_bot.indicators import compute_all_indicators
from nepse_bot.signal_engine import SignalEngine
from nepse_bot.strategy import get_strategy
from nepse_bot.db_manager import db_manager
from nepse_bot.tms_client import tms_client, TMS_BROKER_URLS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, 'templates'))
CORS(app)

# Initialize services
data_fetcher = NepseDataFetcher()
signal_engine = SignalEngine()

# In-memory virtual portfolio
virtual_portfolio = {
    'cash': 1000000,  # Starting with 10 lakh NPR
    'holdings': {},
    'trades': [],
    'initial_capital': 1000000,
}


# ═══════════════════════════════════════
#  Page Routes
# ═══════════════════════════════════════

@app.route('/')
def dashboard():
    """Serve the main dashboard page."""
    return render_template('dashboard.html')


# ═══════════════════════════════════════
#  Stock Data APIs
# ═══════════════════════════════════════

@app.route('/api/stocks')
def get_stocks():
    """Get list of all NEPSE stocks grouped by sector."""
    try:
        stocks = data_fetcher.get_stock_list()
        sectors = data_fetcher.get_sectors()
        return jsonify({
            'success': True,
            'stocks': stocks,
            'sectors': sectors,
            'total': len(stocks),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/stock/<symbol>')
def get_stock_data(symbol):
    """Get historical OHLCV data for a stock."""
    try:
        mode = request.args.get('mode', 'daily')
        days = int(request.args.get('days', 500))

        if mode == 'intraday':
            df = data_fetcher.get_intraday_ohlcv(symbol, days=min(days, 30))
        else:
            df = data_fetcher.get_daily_ohlcv(symbol, days=days)

        if df is None or len(df) == 0:
            return jsonify({'success': False, 'error': f'No data available for {symbol}'}), 404

        # Compute technical indicators (adds indicator series to df)
        indicators = compute_all_indicators(df)

        # Convert to JSON-friendly format
        data = {
            'timestamps': df['timestamps'].dt.strftime('%Y-%m-%d %H:%M:%S').tolist(),
            'open': df['open'].round(2).tolist(),
            'high': df['high'].round(2).tolist(),
            'low': df['low'].round(2).tolist(),
            'close': df['close'].round(2).tolist(),
            'volume': df['volume'].tolist(),
        }

        # Add indicator series for chart overlay
        indicator_series = {}
        for col in ['ema_9', 'ema_20', 'ema_50', 'ema_200', 'sma_20', 'sma_50', 'bb_upper', 'bb_middle', 'bb_lower', 'rsi', 'macd', 'macd_signal', 'macd_hist', 'vwap']:
            if col in df.columns:
                indicator_series[col] = [round(float(v), 2) if pd.notna(v) else None for v in df[col]]

        last_timestamp = df['timestamps'].iloc[-1]
        now = datetime.now()
        diff_minutes = max(0, int((now - last_timestamp).total_seconds() / 60))

        if mode == 'daily':
            status_text = 'Today\'s Daily Session' if last_timestamp.date() == now.date() else f"{(now.date() - last_timestamp.date()).days}d ago"
            display_date = last_timestamp.strftime('%b %d, %Y')
        else:
            display_date = last_timestamp.strftime('%b %d, %Y · %H:%M NPT')
            status_text = 'Live 5min Candle' if diff_minutes < 10 else f'{diff_minutes}m ago'

        # Company fundamentals from Merolagani
        fundamentals = data_fetcher.get_company_fundamentals(symbol)

        return jsonify({
            'success': True,
            'symbol': symbol,
            'mode': mode,
            'data': data,
            'indicators': indicators,
            'indicator_series': indicator_series,
            'fundamentals': fundamentals,
            'rows': len(df),
            'last_price': round(float(df['close'].iloc[-1]), 2),
            'last_date': last_timestamp.strftime('%Y-%m-%d %H:%M'),
            'data_freshness': {
                'latest_date': display_date,
                'is_today': last_timestamp.date() == now.date(),
                'diff_minutes': diff_minutes,
                'status': status_text,
            }
        })

    except Exception as e:
        logger.error(f"Error fetching {symbol}: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/company/<symbol>')
def get_company_details(symbol):
    """Get company fundamentals scraped from Merolagani."""
    try:
        data = data_fetcher.get_company_fundamentals(symbol)
        return jsonify({'success': True, 'fundamentals': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/market/status')
def market_status():
    """Get current NEPSE market status."""
    return jsonify(data_fetcher.get_market_status())


# ═══════════════════════════════════════
#  AI Prediction APIs
# ═══════════════════════════════════════

@app.route('/api/predict/<symbol>', methods=['POST'])
def predict_stock(symbol):
    """Run Kronos AI prediction for a stock."""
    try:
        body = request.get_json() or {}
        mode = body.get('mode', 'daily')
        pred_len = body.get('pred_len', None)
        sample_count = body.get('sample_count', 3)

        # Fetch data
        if mode == 'intraday':
            df = data_fetcher.get_intraday_ohlcv(symbol)
        else:
            df = data_fetcher.get_daily_ohlcv(symbol)

        if df is None or len(df) < 50:
            return jsonify({'success': False, 'error': f'Insufficient data for {symbol}'}), 400

        # Run prediction
        prediction = signal_engine.predict(df, mode=mode, pred_len=pred_len, sample_count=sample_count)

        # Compute indicators for signal generation
        indicators = compute_all_indicators(df.copy())

        # Generate trading signal
        signal = signal_engine.generate_signal(prediction, indicators)

        # Generate trading plan
        strategy = get_strategy(mode)
        plan = strategy.generate_plan(signal, indicators, prediction['current_price'])

        # Format prediction data for frontend
        pred_df = prediction['prediction_df']
        pred_data = {
            'timestamps': pred_df['timestamps'].dt.strftime('%Y-%m-%d %H:%M:%S').tolist() if 'timestamps' in pred_df.columns else [],
            'open': pred_df['open'].round(2).tolist(),
            'high': pred_df['high'].round(2).tolist(),
            'low': pred_df['low'].round(2).tolist(),
            'close': pred_df['close'].round(2).tolist(),
            'volume': pred_df['volume'].astype(int).tolist() if 'volume' in pred_df.columns else [],
        }

        return jsonify({
            'success': True,
            'symbol': symbol,
            'mode': mode,
            'prediction': pred_data,
            'signal': signal,
            'plan': plan,
            'method': prediction['method'],
            'model': prediction.get('model', 'fallback'),
        })

    except Exception as e:
        logger.error(f"Prediction error for {symbol}: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/scan', methods=['POST'])
def scan_market():
    """Scan multiple stocks in parallel and rank by signal strength."""
    try:
        body = request.get_json() or {}
        symbols = body.get('symbols', data_fetcher.get_all_symbols()[:25])
        mode = body.get('mode', 'daily')

        def analyze_single_stock(sym):
            try:
                if mode == 'intraday':
                    df = data_fetcher.get_intraday_ohlcv(sym)
                else:
                    df = data_fetcher.get_daily_ohlcv(sym)

                if df is None or len(df) < 50:
                    return None

                prediction = signal_engine.predict(df, mode=mode, sample_count=1)
                indicators = compute_all_indicators(df)
                signal = signal_engine.generate_signal(prediction, indicators)

                last_price = float(df['close'].iloc[-1])
                pred_df = prediction.get('prediction_df')
                pred_close = float(pred_df['close'].iloc[-1]) if pred_df is not None and 'close' in pred_df.columns and len(pred_df) > 0 else last_price
                change_pct = round(((pred_close - last_price) / last_price) * 100, 2)

                rsi_val = indicators.get('rsi', 50)
                if isinstance(rsi_val, (pd.Series, np.ndarray, list)):
                    rsi_val = float(rsi_val[-1]) if len(rsi_val) > 0 else 50
                if np.isnan(rsi_val):
                    rsi_val = 50.0

                return {
                    'symbol': sym,
                    'signal': signal['signal'],
                    'confidence': signal['confidence'],
                    'color': signal['color'],
                    'price': last_price,
                    'pred_price': pred_close,
                    'change_pct': change_pct,
                    'rsi': round(float(rsi_val), 1),
                    'ema_trend': indicators.get('ema_trend', 'neutral'),
                    'method': prediction.get('method', 'fast_technical'),
                }
            except Exception as e:
                logger.warning(f"Fast scan error for {sym}: {e}")
                return None

        # Execute parallel scans with 12 workers for high speed
        results = []
        with ThreadPoolExecutor(max_workers=12) as executor:
            scanned_items = list(executor.map(analyze_single_stock, symbols))

        results = [item for item in scanned_items if item is not None]

        # Rank: Strong Buy first, then Buy, then Neutral, then Sell
        signal_order = {'STRONG BUY': 0, 'BUY': 1, 'NEUTRAL': 2, 'SELL': 3, 'STRONG SELL': 4}
        results.sort(key=lambda x: (signal_order.get(x['signal'], 5), -x['confidence']))

        return jsonify({
            'success': True,
            'results': results,
            'scanned': len(results),
            'total_requested': len(symbols),
            'mode': mode,
        })

    except Exception as e:
        logger.error(f"Scan error: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ═══════════════════════════════════════
#  Model Management APIs
# ═══════════════════════════════════════

@app.route('/api/model/status')
def model_status():
    """Get Kronos model loading status."""
    return jsonify(signal_engine.get_model_status())


@app.route('/api/model/load', methods=['POST'])
def load_model():
    """Load a Kronos model."""
    body = request.get_json() or {}
    model_key = body.get('model_key', 'kronos-small')
    result = signal_engine.load_model(model_key)
    return jsonify(result)


# ═══════════════════════════════════════
#  Virtual Portfolio APIs
# ═══════════════════════════════════════

@app.route('/api/portfolio', methods=['GET'])
def get_portfolio():
    """Get current virtual portfolio."""
    total_value = virtual_portfolio['cash']
    holdings_detail = []

    for symbol, holding in virtual_portfolio['holdings'].items():
        # Get current price
        df = data_fetcher.get_daily_ohlcv(symbol, days=5)
        current_price = float(df['close'].iloc[-1]) if df is not None and len(df) > 0 else holding['avg_price']
        market_value = current_price * holding['quantity']
        pnl = (current_price - holding['avg_price']) * holding['quantity']
        pnl_pct = ((current_price - holding['avg_price']) / holding['avg_price']) * 100

        total_value += market_value
        holdings_detail.append({
            'symbol': symbol,
            'quantity': holding['quantity'],
            'avg_price': round(holding['avg_price'], 2),
            'current_price': round(current_price, 2),
            'market_value': round(market_value, 2),
            'pnl': round(pnl, 2),
            'pnl_pct': round(pnl_pct, 2),
        })

    overall_pnl = total_value - virtual_portfolio['initial_capital']
    overall_pnl_pct = (overall_pnl / virtual_portfolio['initial_capital']) * 100

    return jsonify({
        'success': True,
        'cash': round(virtual_portfolio['cash'], 2),
        'holdings': holdings_detail,
        'total_value': round(total_value, 2),
        'initial_capital': virtual_portfolio['initial_capital'],
        'overall_pnl': round(overall_pnl, 2),
        'overall_pnl_pct': round(overall_pnl_pct, 2),
        'recent_trades': virtual_portfolio['trades'][-10:],
    })


@app.route('/api/portfolio/trade', methods=['POST'])
def execute_virtual_trade():
    """Execute a virtual trade (paper trading)."""
    try:
        body = request.get_json()
        symbol = body['symbol']
        action = body['action'].upper()  # BUY or SELL
        quantity = int(body['quantity'])
        price = float(body.get('price', 0))

        # Get current price if not specified
        if price == 0:
            df = data_fetcher.get_daily_ohlcv(symbol, days=5)
            if df is not None and len(df) > 0:
                price = float(df['close'].iloc[-1])
            else:
                return jsonify({'success': False, 'error': 'Could not determine price'}), 400

        total_cost = price * quantity

        if action == 'BUY':
            if total_cost > virtual_portfolio['cash']:
                return jsonify({'success': False, 'error': f'Insufficient cash. Need NPR {total_cost:.2f}, have NPR {virtual_portfolio["cash"]:.2f}'}), 400

            virtual_portfolio['cash'] -= total_cost

            if symbol in virtual_portfolio['holdings']:
                h = virtual_portfolio['holdings'][symbol]
                total_qty = h['quantity'] + quantity
                h['avg_price'] = ((h['avg_price'] * h['quantity']) + (price * quantity)) / total_qty
                h['quantity'] = total_qty
            else:
                virtual_portfolio['holdings'][symbol] = {
                    'quantity': quantity,
                    'avg_price': price,
                }

        elif action == 'SELL':
            if symbol not in virtual_portfolio['holdings']:
                return jsonify({'success': False, 'error': f'No holdings in {symbol}'}), 400

            h = virtual_portfolio['holdings'][symbol]
            if quantity > h['quantity']:
                return jsonify({'success': False, 'error': f'Cannot sell {quantity}, only hold {h["quantity"]}'}), 400

            virtual_portfolio['cash'] += total_cost
            h['quantity'] -= quantity

            if h['quantity'] == 0:
                del virtual_portfolio['holdings'][symbol]

        # Record trade
        trade = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'symbol': symbol,
            'action': action,
            'quantity': quantity,
            'price': round(price, 2),
            'total': round(total_cost, 2),
        }
        virtual_portfolio['trades'].append(trade)

        return jsonify({
            'success': True,
            'trade': trade,
            'cash_remaining': round(virtual_portfolio['cash'], 2),
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ═══════════════════════════════════════
#  MySQL Database & Profile APIs
# ═══════════════════════════════════════

@app.route('/api/profile', methods=['GET'])
def get_profile():
    """Get account profile, holdings, and transaction ledger from MySQL."""
    try:
        # Pre-fetch live prices for active holdings if connected
        current_prices = {}
        if db_manager.connected:
            try:
                conn = db_manager.get_connection()
                with conn.cursor() as cur:
                    cur.execute("SELECT `symbol` FROM `holdings`;")
                    symbols = [r['symbol'] for r in cur.fetchall()]
                conn.close()
                for sym in symbols:
                    df = data_fetcher.get_daily_ohlcv(sym, days=5)
                    if df is not None and len(df) > 0:
                        current_prices[sym] = float(df['close'].iloc[-1])
            except Exception as e:
                logger.warning(f"Error fetching current prices for profile: {e}")

        profile_data = db_manager.get_account_profile(current_prices)
        return jsonify(profile_data)
    except Exception as e:
        return jsonify({'connected': False, 'error': str(e)}), 500


@app.route('/api/mysql/config', methods=['POST'])
def save_mysql_config():
    """Save MySQL connection parameters and re-initialize connection."""
    try:
        body = request.get_json() or {}
        res = db_manager.save_config(body)
        return jsonify(res)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/mysql/test', methods=['POST'])
def test_mysql_connection():
    """Test MySQL connection credentials."""
    try:
        body = request.get_json() or {}
        res = db_manager.test_connection(
            host=body.get('host'),
            port=body.get('port'),
            user=body.get('user'),
            password=body.get('password'),
            database=body.get('database')
        )
        return jsonify(res)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/trade/record', methods=['POST'])
def record_mysql_trade():
    """Record an executed or manual trade directly in MySQL ledger."""
    try:
        body = request.get_json() or {}
        symbol = body.get('symbol')
        action = body.get('action')
        quantity = int(body.get('quantity', 0))
        price = float(body.get('price', 0))
        tms_order_no = body.get('tms_order_no')
        trade_type = body.get('trade_type', 'REAL')
        notes = body.get('notes', '')

        if not symbol or not action or quantity <= 0 or price <= 0:
            return jsonify({'success': False, 'error': 'Invalid trade parameters'}), 400

        res = db_manager.record_trade(
            symbol=symbol,
            action=action,
            quantity=quantity,
            price=price,
            tms_order_no=tms_order_no,
            trade_type=trade_type,
            notes=notes
        )
        return jsonify(res)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/profile/cash', methods=['POST'])
def update_profile_cash():
    """Set or deposit real cash funds into the account."""
    try:
        body = request.get_json() or {}
        amount = float(body.get('amount', 0))
        is_deposit = bool(body.get('is_deposit', False))
        res = db_manager.update_cash_balance(amount, is_deposit)
        return jsonify(res)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ═══════════════════════════════════════
#  TMS (Real Trading) API Routes
# ═══════════════════════════════════════

@app.route('/api/tms/brokers', methods=['GET'])
def get_tms_brokers():
    """Return list of supported TMS broker numbers and URLs."""
    brokers = [{'number': k, 'url': v, 'label': f'Broker {k} ({v.replace("https://", "")})'}
               for k, v in TMS_BROKER_URLS.items()]
    return jsonify({'success': True, 'brokers': brokers})


@app.route('/api/tms/status', methods=['GET'])
def get_tms_status():
    """Get current TMS login status and client info."""
    info = tms_client.get_client_info()
    return jsonify({'success': True, **info})


@app.route('/api/tms/login', methods=['POST'])
def tms_login():
    """Authenticate with TMS broker and store session token."""
    try:
        body = request.get_json() or {}
        broker = body.get('broker', '29')
        username = body.get('username', '')
        password = body.get('password', '')

        if not username or not password:
            return jsonify({'success': False, 'error': 'Username and password are required'}), 400

        # Save broker config
        tms_client.save_config(broker, username, password)

        # Attempt login
        result = tms_client.login(username, password)
        if result.get('success'):
            client_data = result.get('client', {})
            return jsonify({
                'success': True,
                'message': f'Logged into TMS Broker {broker} successfully',
                'client_name': client_data.get('fullName', username),
                'broker': broker,
                'base_url': tms_client.base_url,
            })
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Login failed')}), 401
    except Exception as e:
        logger.error(f'TMS login error: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tms/set-token', methods=['POST'])
def tms_set_token():
    """Directly set active TMS session token from user browser."""
    try:
        body = request.get_json() or {}
        token = body.get('token', '').strip()
        broker = body.get('broker', '29')
        client_name = body.get('client_name', 'TMS User')

        if not token:
            return jsonify({'success': False, 'error': 'Token is required'}), 400

        tms_client.save_config(broker, client_name, '')
        result = tms_client.set_token(token, client_name)
        return jsonify(result)
    except Exception as e:
        logger.error(f'TMS set-token error: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tms/logout', methods=['POST'])
def tms_logout():
    """Logout from TMS."""
    tms_client.logout()
    return jsonify({'success': True, 'message': 'Logged out from TMS'})


@app.route('/api/tms/order', methods=['POST'])
def tms_place_order():
    """Place a real BUY or SELL order on TMS."""
    try:
        body = request.get_json() or {}
        symbol = body.get('symbol', '').upper().strip()
        action = body.get('action', '').upper().strip()
        quantity = int(body.get('quantity', 0))
        price = float(body.get('price', 0))
        order_type = body.get('order_type', 'RL')

        if not symbol:
            return jsonify({'success': False, 'error': 'Stock symbol is required'}), 400
        if action not in ('BUY', 'SELL'):
            return jsonify({'success': False, 'error': 'Action must be BUY or SELL'}), 400
        if quantity <= 0:
            return jsonify({'success': False, 'error': 'Quantity must be > 0'}), 400
        if price <= 0:
            return jsonify({'success': False, 'error': 'Price must be > 0'}), 400

        if not tms_client.is_logged_in:
            return jsonify({'success': False, 'error': 'Not logged into TMS. Please login first.', 'need_login': True}), 401

        result = tms_client.place_order(
            symbol=symbol,
            action=action,
            quantity=quantity,
            price=price,
            order_type=order_type,
        )

        # If successful, also log to MySQL if connected
        if result.get('success') and db_manager.connected:
            try:
                db_manager.record_trade(
                    symbol=symbol,
                    action=action,
                    quantity=quantity,
                    price=price,
                    tms_order_no=result['order']['order_id'],
                    trade_type='REAL',
                    notes=f'TMS {action} order via Kronos AI'
                )
            except Exception as db_err:
                logger.warning(f'TMS order placed but MySQL logging failed: {db_err}')

        return jsonify(result)
    except Exception as e:
        logger.error(f'TMS order placement error: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tms/portfolio', methods=['GET'])
def tms_get_portfolio():
    """Fetch TMS real portfolio holdings and cash balance."""
    try:
        if not tms_client.is_logged_in:
            return jsonify({'success': False, 'error': 'Not logged into TMS', 'need_login': True}), 401
        result = tms_client.get_portfolio()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tms/orders', methods=['GET'])
def tms_get_orders():
    """Fetch today's TMS order list."""
    try:
        if not tms_client.is_logged_in:
            return jsonify({'success': False, 'error': 'Not logged into TMS', 'need_login': True}), 401
        result = tms_client.get_my_orders()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tms/cancel/<order_id>', methods=['DELETE'])
def tms_cancel_order(order_id):
    """Cancel a pending TMS order."""
    try:
        if not tms_client.is_logged_in:
            return jsonify({'success': False, 'error': 'Not logged into TMS', 'need_login': True}), 401
        result = tms_client.cancel_order(order_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tms/depth/<symbol>', methods=['GET'])
def tms_market_depth(symbol):
    """Get live market depth for a symbol."""
    try:
        if not tms_client.is_logged_in:
            return jsonify({'success': False, 'error': 'Not logged into TMS', 'need_login': True}), 401
        result = tms_client.get_market_depth(symbol)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ═══════════════════════════════════════
#  App Factory
# ═══════════════════════════════════════

def create_app():
    """Create and configure the Flask app."""
    return app


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("  🇳🇵 NEPSE AI Trading Bot — Powered by Kronos")
    print("=" * 60)
    print(f"  Device: {signal_engine.device}")
    print(f"  Kronos Available: {signal_engine._model_available}")
    print(f"  Dashboard: http://localhost:8888")
    print("=" * 60 + "\n")

    app.run(debug=True, host='0.0.0.0', port=8888)
