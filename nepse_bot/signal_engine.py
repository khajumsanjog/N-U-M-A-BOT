"""
AI Signal Engine
=================
Uses the Kronos foundation model to predict future candlesticks for NEPSE stocks
and generates actionable BUY/SELL/HOLD signals with confidence scores.

Optimized for Apple Silicon (M3) using MPS backend.
"""

import os
import sys
import logging
import numpy as np
import pandas as pd
import torch
from datetime import timedelta

# Add project root for Kronos imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


class SignalEngine:
    """
    AI-powered signal generator using the Kronos candlestick foundation model.
    """

    AVAILABLE_MODELS = {
        'kronos-mini': {
            'name': 'Kronos-mini',
            'model_id': 'NeoQuasar/Kronos-mini',
            'tokenizer_id': 'NeoQuasar/Kronos-Tokenizer-2k',
            'context_length': 2048,
            'params': '4.1M',
            'description': 'Lightweight — fast predictions, lower accuracy'
        },
        'kronos-small': {
            'name': 'Kronos-small',
            'model_id': 'NeoQuasar/Kronos-small',
            'tokenizer_id': 'NeoQuasar/Kronos-Tokenizer-base',
            'context_length': 512,
            'params': '24.7M',
            'description': 'Balanced — good accuracy, reasonable speed'
        },
        'kronos-base': {
            'name': 'Kronos-base',
            'model_id': 'NeoQuasar/Kronos-base',
            'tokenizer_id': 'NeoQuasar/Kronos-Tokenizer-base',
            'context_length': 512,
            'params': '102.3M',
            'description': 'Best accuracy — slower on CPU, fine on MPS'
        },
    }

    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.predictor = None
        self.model_key = None
        self.device = self._detect_device()
        self.is_loaded = False
        self._model_available = False

        # Check if Kronos model code is importable
        try:
            from model import Kronos, KronosTokenizer, KronosPredictor
            self._model_available = True
        except ImportError:
            logger.warning("Kronos model not importable — will use fallback prediction")

    def _detect_device(self):
        """Detect best available device: MPS (Apple Silicon) > CUDA > CPU."""
        if torch.backends.mps.is_available():
            logger.info("🍎 Apple Silicon MPS detected — using GPU acceleration")
            return 'mps'
        elif torch.cuda.is_available():
            logger.info("🟢 CUDA GPU detected")
            return 'cuda'
        else:
            logger.info("Using CPU for inference")
            return 'cpu'

    def get_model_status(self):
        """Get current model loading status."""
        return {
            'available': self._model_available,
            'loaded': self.is_loaded,
            'model_key': self.model_key,
            'device': self.device,
            'models': self.AVAILABLE_MODELS,
        }

    def load_model(self, model_key='kronos-small'):
        """
        Load a Kronos model from HuggingFace Hub.
        Downloads on first use (~100MB for kronos-small).
        """
        if not self._model_available:
            return {'success': False, 'error': 'Kronos model code not found. Ensure model/ directory is accessible.'}

        if model_key not in self.AVAILABLE_MODELS:
            return {'success': False, 'error': f'Unknown model: {model_key}'}

        config = self.AVAILABLE_MODELS[model_key]

        try:
            from model import Kronos, KronosTokenizer, KronosPredictor

            logger.info(f"Loading {config['name']} ({config['params']})...")

            self.tokenizer = KronosTokenizer.from_pretrained(config['tokenizer_id'])
            self.model = Kronos.from_pretrained(config['model_id'])

            # For MPS, we need to be careful — Kronos uses some ops not yet on MPS
            # Fall back to CPU if MPS fails
            effective_device = self.device
            try:
                self.predictor = KronosPredictor(
                    self.model, self.tokenizer,
                    device=effective_device,
                    max_context=config['context_length']
                )
            except Exception as e:
                logger.warning(f"MPS failed ({e}), falling back to CPU")
                effective_device = 'cpu'
                self.predictor = KronosPredictor(
                    self.model, self.tokenizer,
                    device='cpu',
                    max_context=config['context_length']
                )
                self.device = 'cpu'

            self.model_key = model_key
            self.is_loaded = True

            return {
                'success': True,
                'message': f'✅ Loaded {config["name"]} ({config["params"]}) on {effective_device}',
                'model': config,
                'device': effective_device,
            }

        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return {'success': False, 'error': str(e)}

    def predict(self, df, mode='daily', pred_len=None, sample_count=3):
        """
        Run Kronos prediction on OHLCV DataFrame.

        Args:
            df: Kronos-compatible DataFrame with [timestamps, open, high, low, close, volume]
            mode: 'daily' or 'intraday'
            pred_len: Number of candles to predict (default: 10 for daily, 24 for intraday)
            sample_count: Number of prediction samples for confidence estimation

        Returns:
            dict with prediction_df, signal, confidence, etc.
        """
        if pred_len is None:
            pred_len = 10 if mode == 'daily' else 24

        # Use Kronos model if available
        if self.is_loaded and self.predictor is not None:
            return self._predict_with_kronos(df, pred_len, sample_count)
        else:
            return self._predict_fallback(df, pred_len, mode)

    def _predict_with_kronos(self, df, pred_len, sample_count):
        """Run actual Kronos model prediction."""
        try:
            config = self.AVAILABLE_MODELS[self.model_key]
            max_context = config['context_length']

            # Prepare data — truncate to max context
            lookback = min(len(df), max_context)
            x_df = df.iloc[-lookback:][['open', 'high', 'low', 'close', 'volume']].copy()

            # Add amount column if missing (Kronos expects it optionally)
            if 'amount' not in x_df.columns:
                x_df['amount'] = 0

            x_timestamp = pd.Series(df.iloc[-lookback:]['timestamps'].values, name='timestamps')

            # Generate future timestamps
            last_ts = df['timestamps'].iloc[-1]
            if len(df) > 1:
                time_diff = df['timestamps'].iloc[-1] - df['timestamps'].iloc[-2]
            else:
                time_diff = timedelta(days=1)

            y_timestamps = pd.Series(
                pd.date_range(start=last_ts + time_diff, periods=pred_len, freq=time_diff),
                name='timestamps'
            )

            # Run multiple predictions for confidence estimation
            all_preds = []
            for i in range(sample_count):
                pred_df = self.predictor.predict(
                    df=x_df.reset_index(drop=True),
                    x_timestamp=x_timestamp.reset_index(drop=True),
                    y_timestamp=y_timestamps.reset_index(drop=True),
                    pred_len=pred_len,
                    T=0.8,
                    top_p=0.9,
                    sample_count=1
                )
                all_preds.append(pred_df)

            # Average predictions
            avg_pred = all_preds[0].copy()
            for col in ['open', 'high', 'low', 'close']:
                vals = np.array([p[col].values for p in all_preds])
                avg_pred[col] = vals.mean(axis=0)
                if 'volume' in avg_pred.columns:
                    vol_vals = np.array([p['volume'].values for p in all_preds])
                    avg_pred['volume'] = vol_vals.mean(axis=0)

            # Compute confidence from prediction consistency
            close_preds = np.array([p['close'].values for p in all_preds])
            pred_std = close_preds.std(axis=0).mean()
            current_price = df['close'].iloc[-1]
            consistency = 1.0 - min(pred_std / (current_price * 0.05), 1.0)

            avg_pred['timestamps'] = y_timestamps.values

            return {
                'prediction_df': avg_pred,
                'current_price': current_price,
                'predicted_close': float(avg_pred['close'].iloc[-1]),
                'consistency': float(consistency),
                'method': 'kronos',
                'model': self.model_key,
                'sample_count': sample_count,
            }

        except Exception as e:
            logger.error(f"Kronos prediction failed: {e}")
            return self._predict_fallback(df, pred_len, 'daily')

    def _predict_fallback(self, df, pred_len, mode):
        """
        Fallback prediction using technical analysis when Kronos is not loaded.
        Uses EMA trend extrapolation + momentum.
        """
        close = df['close'].values
        current_price = close[-1]

        # Calculate trend from EMA
        ema_20 = pd.Series(close).ewm(span=20, adjust=False).mean().values
        ema_50 = pd.Series(close).ewm(span=50, adjust=False).mean().values

        # Trend direction and strength
        trend = (ema_20[-1] - ema_50[-1]) / current_price
        momentum = (close[-1] - close[-5]) / close[-5] if len(close) >= 5 else 0

        # Project future prices
        daily_return = trend * 0.3 + momentum * 0.1
        noise_scale = np.std(np.diff(close[-20:]) / close[-20:-1]) if len(close) > 20 else 0.01

        np.random.seed(42)
        predicted_close = np.zeros(pred_len)
        predicted_close[0] = current_price * (1 + daily_return)

        for i in range(1, pred_len):
            noise = np.random.normal(0, noise_scale)
            mean_rev = -0.05 * (predicted_close[i - 1] - current_price) / current_price
            predicted_close[i] = predicted_close[i - 1] * (1 + daily_return + noise + mean_rev)

        # Generate OHLC from predicted close
        volatility = noise_scale * current_price
        predicted_high = predicted_close + abs(np.random.normal(0, volatility, pred_len)) * 0.7
        predicted_low = predicted_close - abs(np.random.normal(0, volatility, pred_len)) * 0.7
        predicted_open = np.roll(predicted_close, 1)
        predicted_open[0] = current_price

        # Generate timestamps
        last_ts = df['timestamps'].iloc[-1]
        if len(df) > 1:
            time_diff = df['timestamps'].iloc[-1] - df['timestamps'].iloc[-2]
        else:
            time_diff = timedelta(days=1)

        timestamps = pd.date_range(start=last_ts + time_diff, periods=pred_len, freq=time_diff)

        pred_df = pd.DataFrame({
            'timestamps': timestamps,
            'open': np.round(predicted_open, 2),
            'high': np.round(predicted_high, 2),
            'low': np.round(predicted_low, 2),
            'close': np.round(predicted_close, 2),
            'volume': np.random.randint(1000, 50000, pred_len),
        })

        return {
            'prediction_df': pred_df,
            'current_price': current_price,
            'predicted_close': float(predicted_close[-1]),
            'consistency': 0.55,  # Lower confidence for fallback
            'method': 'technical_fallback',
            'model': 'ema_momentum',
            'sample_count': 1,
        }

    def generate_signal(self, prediction_result, indicators=None):
        """
        Generate a BUY/SELL/HOLD signal from prediction results and technical indicators.

        Returns:
            dict with signal, confidence, reasoning, targets
        """
        current_price = prediction_result['current_price']
        predicted_close = prediction_result['predicted_close']
        consistency = prediction_result['consistency']

        # Price change prediction
        price_change_pct = ((predicted_close - current_price) / current_price) * 100

        # === AI Score (50% weight) ===
        ai_score = 0
        if price_change_pct > 3:
            ai_score = 90
        elif price_change_pct > 1.5:
            ai_score = 70
        elif price_change_pct > 0.5:
            ai_score = 55
        elif price_change_pct > -0.5:
            ai_score = 50
        elif price_change_pct > -1.5:
            ai_score = 35
        elif price_change_pct > -3:
            ai_score = 20
        else:
            ai_score = 10

        # Adjust by prediction consistency
        ai_score = ai_score * (0.5 + 0.5 * consistency)

        # === Technical Score (30% weight) ===
        tech_score = 50  # Neutral default
        tech_reasons = []

        if indicators:
            rsi = indicators.get('rsi', 50)
            macd_cross = indicators.get('macd_cross', 'NEUTRAL')
            ema_trend = indicators.get('ema_trend', 'NEUTRAL')
            bb_position = indicators.get('bb_position', 'MIDDLE')

            # RSI component
            if rsi < 30:
                tech_score += 15
                tech_reasons.append(f"RSI oversold ({rsi:.0f})")
            elif rsi > 70:
                tech_score -= 15
                tech_reasons.append(f"RSI overbought ({rsi:.0f})")

            # MACD component
            if macd_cross in ['BULLISH_CROSS', 'BULLISH']:
                tech_score += 12
                tech_reasons.append(f"MACD {macd_cross.lower()}")
            elif macd_cross in ['BEARISH_CROSS', 'BEARISH']:
                tech_score -= 12
                tech_reasons.append(f"MACD {macd_cross.lower()}")

            # EMA trend
            if ema_trend == 'STRONG_BULLISH':
                tech_score += 15
                tech_reasons.append("Strong uptrend (EMA)")
            elif ema_trend == 'BULLISH':
                tech_score += 8
                tech_reasons.append("Uptrend (EMA)")
            elif ema_trend == 'STRONG_BEARISH':
                tech_score -= 15
                tech_reasons.append("Strong downtrend (EMA)")
            elif ema_trend == 'BEARISH':
                tech_score -= 8
                tech_reasons.append("Downtrend (EMA)")

            # Bollinger Bands
            if bb_position == 'BELOW_LOWER':
                tech_score += 10
                tech_reasons.append("Below lower Bollinger Band")
            elif bb_position == 'ABOVE_UPPER':
                tech_score -= 10
                tech_reasons.append("Above upper Bollinger Band")

        tech_score = max(0, min(100, tech_score))

        # === Volume Score (20% weight) ===
        vol_score = 50  # Neutral for now, enhanced when live data available

        # === Composite Signal ===
        composite = (ai_score * 0.50) + (tech_score * 0.30) + (vol_score * 0.20)
        composite = max(0, min(100, composite))

        # Determine signal
        if composite >= 72:
            signal = 'STRONG BUY'
            color = '#00e676'
        elif composite >= 58:
            signal = 'BUY'
            color = '#4caf50'
        elif composite >= 42:
            signal = 'HOLD'
            color = '#ff9800'
        elif composite >= 28:
            signal = 'SELL'
            color = '#f44336'
        else:
            signal = 'STRONG SELL'
            color = '#d50000'

        # Calculate targets
        pred_df = prediction_result['prediction_df']
        pred_highs = pred_df['high'].values
        pred_lows = pred_df['low'].values

        target_price = float(np.percentile(pred_df['close'].values, 75))
        stop_loss = float(np.min(pred_lows)) * 0.98

        # Risk/Reward ratio
        potential_gain = target_price - current_price
        potential_loss = current_price - stop_loss
        risk_reward = potential_gain / potential_loss if potential_loss > 0 else 0

        return {
            'signal': signal,
            'color': color,
            'confidence': round(composite, 1),
            'price_change_pct': round(price_change_pct, 2),
            'current_price': round(current_price, 2),
            'predicted_close': round(predicted_close, 2),
            'target_price': round(target_price, 2),
            'stop_loss': round(stop_loss, 2),
            'risk_reward': round(risk_reward, 2),
            'scores': {
                'ai': round(ai_score, 1),
                'technical': round(tech_score, 1),
                'volume': round(vol_score, 1),
                'composite': round(composite, 1),
            },
            'reasoning': {
                'ai': f"Kronos predicts {price_change_pct:+.2f}% price change (consistency: {consistency:.0%})",
                'technical': tech_reasons if tech_reasons else ['No strong technical signals'],
                'method': prediction_result['method'],
            },
        }
