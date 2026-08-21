"""
Trading Strategy Engine
========================
Combines Kronos AI predictions with technical indicators to generate
actionable trading signals for both intraday and swing trading on NEPSE.
"""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class IntradayStrategy:
    """
    Intraday trading strategy for NEPSE (11:00 AM - 3:00 PM NPT).
    Uses 5-minute candle data + Kronos short-term forecast.
    """

    # NEPSE-specific rules
    CIRCUIT_LIMIT_PCT = 10  # NEPSE has 10% circuit breaker
    MIN_PROFIT_PCT = 0.5   # Minimum target for intraday
    MAX_LOSS_PCT = 1.0     # Maximum stop loss for intraday

    def generate_plan(self, signal_result, indicators, current_price):
        """
        Generate an intraday trading plan.
        Returns: dict with entry, exit, stop_loss, time constraints.
        """
        signal = signal_result['signal']
        confidence = signal_result['confidence']
        predicted_close = signal_result['predicted_close']

        plan = {
            'mode': 'INTRADAY',
            'signal': signal,
            'confidence': confidence,
            'current_price': current_price,
        }

        if signal in ['STRONG BUY', 'BUY']:
            # Calculate entry zone
            entry_low = current_price * 0.998  # Slight dip entry
            entry_high = current_price * 1.002

            # Target based on ATR
            atr = indicators.get('atr', current_price * 0.015)
            target_1 = current_price + (atr * 0.8)
            target_2 = current_price + (atr * 1.5)

            # Stop loss
            stop_loss = current_price - (atr * 0.6)

            plan.update({
                'action': 'BUY',
                'entry_zone': f"NPR {entry_low:.2f} - {entry_high:.2f}",
                'target_1': round(target_1, 2),
                'target_2': round(target_2, 2),
                'stop_loss': round(stop_loss, 2),
                'risk_pct': round(((current_price - stop_loss) / current_price) * 100, 2),
                'reward_pct': round(((target_1 - current_price) / current_price) * 100, 2),
                'exit_time': '14:30',  # Exit 30 min before market close
                'notes': [
                    'Enter on pullback near support',
                    'Trail stop loss after Target 1 hit',
                    'Must exit by 14:30 — no overnight hold',
                    f'Max position: 2-3% of capital',
                ],
            })

        elif signal in ['STRONG SELL', 'SELL']:
            plan.update({
                'action': 'AVOID / EXIT',
                'notes': [
                    'Do not initiate new long positions',
                    'If holding, consider exiting on bounces',
                    'Wait for reversal confirmation before buying',
                ],
            })

        else:
            plan.update({
                'action': 'WAIT',
                'notes': [
                    'No clear intraday setup',
                    'Wait for strong signal with confidence > 60%',
                    'Monitor for breakout above resistance or breakdown below support',
                ],
            })

        return plan


class SwingStrategy:
    """
    Swing/Positional trading strategy for NEPSE.
    Uses daily candle data + Kronos multi-day forecast.
    Typical hold period: 3-15 trading days.
    """

    MIN_PROFIT_PCT = 3.0   # Minimum target for swing
    MAX_LOSS_PCT = 5.0     # Maximum stop loss for swing

    def generate_plan(self, signal_result, indicators, current_price):
        """
        Generate a swing trading plan.
        Returns: dict with entry, targets, stop_loss, hold duration.
        """
        signal = signal_result['signal']
        confidence = signal_result['confidence']
        predicted_close = signal_result['predicted_close']
        price_change = signal_result['price_change_pct']

        plan = {
            'mode': 'SWING',
            'signal': signal,
            'confidence': confidence,
            'current_price': current_price,
        }

        if signal in ['STRONG BUY', 'BUY']:
            # Support/Resistance for targets
            sr = indicators.get('support_resistance', {'support': [], 'resistance': []})

            # ATR-based targets
            atr = indicators.get('atr', current_price * 0.02)

            target_1 = current_price + (atr * 2)
            target_2 = current_price + (atr * 3.5)
            target_3 = predicted_close if predicted_close > current_price else target_2

            # If we have resistance levels, use them
            if sr['resistance']:
                target_1 = min(target_1, sr['resistance'][0])
                if len(sr['resistance']) > 1:
                    target_2 = sr['resistance'][1]

            stop_loss = current_price - (atr * 1.5)
            if sr['support']:
                stop_loss = max(stop_loss, sr['support'][-1] * 0.98)

            # Position sizing recommendation
            risk_per_share = current_price - stop_loss
            reward_per_share = target_1 - current_price

            plan.update({
                'action': 'BUY',
                'entry_zone': f"NPR {current_price * 0.995:.2f} - {current_price * 1.005:.2f}",
                'target_1': round(target_1, 2),
                'target_2': round(target_2, 2),
                'target_3': round(target_3, 2),
                'stop_loss': round(stop_loss, 2),
                'risk_pct': round((risk_per_share / current_price) * 100, 2),
                'reward_pct': round((reward_per_share / current_price) * 100, 2),
                'risk_reward': round(reward_per_share / risk_per_share, 2) if risk_per_share > 0 else 0,
                'hold_duration': '5-10 trading days' if confidence > 65 else '3-5 trading days',
                'position_size': '3-5% of portfolio' if confidence > 70 else '2-3% of portfolio',
                'notes': [
                    f'AI predicts {price_change:+.1f}% move over forecast period',
                    f'EMA trend: {indicators.get("ema_trend", "N/A")}',
                    f'RSI: {indicators.get("rsi", "N/A")} ({indicators.get("rsi_signal", "N/A")})',
                    'Book 50% at Target 1, trail rest',
                    'Move stop to breakeven after Target 1',
                ],
            })

        elif signal in ['STRONG SELL', 'SELL']:
            plan.update({
                'action': 'SELL / AVOID',
                'hold_duration': 'N/A',
                'notes': [
                    f'AI predicts {price_change:+.1f}% decline',
                    'Exit existing positions on bounces',
                    f'Wait for RSI < 30 for potential bottom ({indicators.get("rsi", "N/A")} currently)',
                    'Do not average down against the trend',
                ],
            })

        else:
            plan.update({
                'action': 'HOLD / WAIT',
                'hold_duration': 'N/A',
                'notes': [
                    'No clear directional signal',
                    'Market may be in consolidation',
                    'Wait for breakout confirmation',
                    f'Watch for MACD crossover (currently: {indicators.get("macd_cross", "N/A")})',
                ],
            })

        return plan


def get_strategy(mode):
    """Factory function to get strategy by mode."""
    if mode == 'intraday':
        return IntradayStrategy()
    else:
        return SwingStrategy()
