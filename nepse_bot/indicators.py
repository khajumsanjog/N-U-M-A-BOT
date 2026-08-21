"""
Technical Indicators Module
============================
Pure NumPy/Pandas implementations of common technical analysis indicators.
No external TA library dependency — works everywhere.
"""

import numpy as np
import pandas as pd


def compute_rsi(series, period=14):
    """
    Compute Relative Strength Index (RSI).
    RSI > 70 = Overbought (potential sell)
    RSI < 30 = Oversold (potential buy)
    """
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    # Use Wilder's smoothing after initial SMA
    for i in range(period, len(series)):
        avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (period - 1) + loss.iloc[i]) / period

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def compute_macd(series, fast=12, slow=26, signal=9):
    """
    Compute MACD (Moving Average Convergence Divergence).
    Returns: macd_line, signal_line, histogram
    """
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def compute_ema(series, period):
    """Compute Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def compute_sma(series, period):
    """Compute Simple Moving Average."""
    return series.rolling(window=period, min_periods=1).mean()


def compute_bollinger_bands(series, period=20, std_dev=2):
    """
    Compute Bollinger Bands.
    Returns: upper_band, middle_band (SMA), lower_band
    """
    middle = series.rolling(window=period, min_periods=1).mean()
    std = series.rolling(window=period, min_periods=1).std()
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    return upper, middle, lower


def compute_vwap(df):
    """
    Compute Volume Weighted Average Price (VWAP).
    Best for intraday analysis.
    """
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    cumulative_tp_vol = (typical_price * df['volume']).cumsum()
    cumulative_vol = df['volume'].cumsum()
    vwap = cumulative_tp_vol / cumulative_vol.replace(0, np.nan)
    return vwap.fillna(typical_price)


def compute_atr(df, period=14):
    """Compute Average True Range (ATR) for volatility measurement."""
    high = df['high']
    low = df['low']
    close = df['close']

    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.rolling(window=period, min_periods=1).mean()
    return atr


def find_support_resistance(df, window=20, num_levels=3):
    """
    Find key support and resistance levels using pivot points and local extrema.
    Returns: dict with support[] and resistance[] price levels.
    """
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values

    # Find local minima (support) and maxima (resistance)
    supports = []
    resistances = []

    for i in range(window, len(close) - window):
        # Local minimum check
        if low[i] == min(low[i - window:i + window + 1]):
            supports.append(low[i])
        # Local maximum check
        if high[i] == max(high[i - window:i + window + 1]):
            resistances.append(high[i])

    # Cluster nearby levels and take the strongest
    def cluster_levels(levels, threshold_pct=0.02):
        if not levels:
            return []
        levels = sorted(levels)
        clustered = []
        current_cluster = [levels[0]]
        for lvl in levels[1:]:
            if (lvl - current_cluster[-1]) / current_cluster[-1] < threshold_pct:
                current_cluster.append(lvl)
            else:
                clustered.append(np.mean(current_cluster))
                current_cluster = [lvl]
        clustered.append(np.mean(current_cluster))
        return clustered

    supports = cluster_levels(supports)[-num_levels:]
    resistances = cluster_levels(resistances)[:num_levels]

    return {
        'support': [round(s, 2) for s in supports],
        'resistance': [round(r, 2) for r in resistances],
    }


def compute_all_indicators(df):
    """
    Compute all technical indicators for a given OHLCV DataFrame.
    Adds indicator columns directly to the DataFrame.
    Returns: dict summary of current indicator readings.
    """
    close = df['close']

    # RSI
    df['rsi'] = compute_rsi(close)

    # MACD
    df['macd'], df['macd_signal'], df['macd_hist'] = compute_macd(close)

    # EMAs
    df['ema_9'] = compute_ema(close, 9)
    df['ema_20'] = compute_ema(close, 20)
    df['ema_50'] = compute_ema(close, 50)
    df['ema_200'] = compute_ema(close, 200)

    # SMAs
    df['sma_20'] = compute_sma(close, 20)
    df['sma_50'] = compute_sma(close, 50)

    # Bollinger Bands
    df['bb_upper'], df['bb_middle'], df['bb_lower'] = compute_bollinger_bands(close)

    # VWAP
    df['vwap'] = compute_vwap(df)

    # ATR
    df['atr'] = compute_atr(df)

    # Current readings (last row)
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last

    # RSI signal
    rsi_val = last['rsi']
    if rsi_val > 70:
        rsi_signal = 'OVERBOUGHT'
    elif rsi_val < 30:
        rsi_signal = 'OVERSOLD'
    else:
        rsi_signal = 'NEUTRAL'

    # MACD signal
    macd_cross = 'NEUTRAL'
    if last['macd'] > last['macd_signal'] and prev['macd'] <= prev['macd_signal']:
        macd_cross = 'BULLISH_CROSS'
    elif last['macd'] < last['macd_signal'] and prev['macd'] >= prev['macd_signal']:
        macd_cross = 'BEARISH_CROSS'
    elif last['macd'] > last['macd_signal']:
        macd_cross = 'BULLISH'
    elif last['macd'] < last['macd_signal']:
        macd_cross = 'BEARISH'

    # EMA trend
    ema_trend = 'NEUTRAL'
    if last['ema_9'] > last['ema_20'] > last['ema_50']:
        ema_trend = 'STRONG_BULLISH'
    elif last['ema_9'] > last['ema_20']:
        ema_trend = 'BULLISH'
    elif last['ema_9'] < last['ema_20'] < last['ema_50']:
        ema_trend = 'STRONG_BEARISH'
    elif last['ema_9'] < last['ema_20']:
        ema_trend = 'BEARISH'

    # Bollinger Band position
    bb_position = 'MIDDLE'
    if last['close'] >= last['bb_upper']:
        bb_position = 'ABOVE_UPPER'
    elif last['close'] <= last['bb_lower']:
        bb_position = 'BELOW_LOWER'

    # Support/Resistance
    sr_levels = find_support_resistance(df)

    return {
        'rsi': round(rsi_val, 2),
        'rsi_signal': rsi_signal,
        'macd': round(last['macd'], 4),
        'macd_signal_val': round(last['macd_signal'], 4),
        'macd_histogram': round(last['macd_hist'], 4),
        'macd_cross': macd_cross,
        'ema_9': round(last['ema_9'], 2),
        'ema_20': round(last['ema_20'], 2),
        'ema_50': round(last['ema_50'], 2),
        'ema_trend': ema_trend,
        'bb_upper': round(last['bb_upper'], 2),
        'bb_middle': round(last['bb_middle'], 2),
        'bb_lower': round(last['bb_lower'], 2),
        'bb_position': bb_position,
        'vwap': round(last['vwap'], 2),
        'atr': round(last['atr'], 2),
        'support_resistance': sr_levels,
    }
