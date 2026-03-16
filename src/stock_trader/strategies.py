"""
Collection of day trading strategies.

Each strategy function takes (ticker, bars, positions) and returns a Signal.
Bars is the full history of Bar objects for that ticker.
"""
import pandas as pd
import pandas_ta as ta

from stock_trader.models import Bar, Signal


def _bars_to_df(bars: list[Bar]) -> pd.DataFrame:
    """Convert bars to a DataFrame."""
    return pd.DataFrame([
        {"open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume}
        for b in bars
    ])


# ---------------------------------------------------------------------------
# 1. VWAP — Volume Weighted Average Price
# ---------------------------------------------------------------------------
# Buy when price crosses below VWAP (cheap relative to volume-weighted avg)
# Sell when price crosses above VWAP (expensive relative to volume-weighted avg)

def evaluate_vwap(ticker: str, bars: list[Bar], positions: dict | None = None) -> Signal:
    if len(bars) < 20:
        return Signal(ticker=ticker, action="HOLD", confidence=0.0, reason="Insufficient data")

    df = _bars_to_df(bars)
    has_position = ticker in (positions or {})

    # Calculate VWAP: cumulative(price * volume) / cumulative(volume)
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    cum_vol = df["volume"].cumsum()
    cum_tp_vol = (typical_price * df["volume"]).cumsum()
    vwap = cum_tp_vol / cum_vol

    current_price = df["close"].iloc[-1]
    current_vwap = vwap.iloc[-1]
    prev_price = df["close"].iloc[-2]
    prev_vwap = vwap.iloc[-2]

    # Distance from VWAP as percentage
    distance_pct = (current_price - current_vwap) / current_vwap * 100

    # BUY: price crosses above VWAP from below (bullish crossover)
    if prev_price < prev_vwap and current_price > current_vwap:
        confidence = min(abs(distance_pct) / 0.5, 1.0)
        return Signal(ticker=ticker, action="BUY", confidence=max(confidence, 0.5),
                       reason=f"VWAP bullish crossover ({distance_pct:+.2f}% from VWAP)")

    # SELL: price crosses below VWAP from above (bearish crossover)
    if prev_price > prev_vwap and current_price < current_vwap:
        confidence = min(abs(distance_pct) / 0.5, 1.0)
        return Signal(ticker=ticker, action="SELL", confidence=max(confidence, 0.5),
                       reason=f"VWAP bearish crossover ({distance_pct:+.2f}% from VWAP)")

    # BUY: price well below VWAP (mean reversion opportunity)
    if distance_pct < -0.3 and not has_position:
        return Signal(ticker=ticker, action="BUY", confidence=0.6,
                       reason=f"Price {distance_pct:.2f}% below VWAP")

    # SELL: price well above VWAP with position
    if distance_pct > 0.3 and has_position:
        return Signal(ticker=ticker, action="SELL", confidence=0.6,
                       reason=f"Price {distance_pct:.2f}% above VWAP")

    return Signal(ticker=ticker, action="HOLD", confidence=0.0,
                   reason=f"Near VWAP ({distance_pct:+.2f}%)")


# ---------------------------------------------------------------------------
# 2. EMA Crossover (9/21)
# ---------------------------------------------------------------------------
# Buy when fast EMA (9) crosses above slow EMA (21) — bullish momentum
# Sell when fast EMA crosses below slow EMA — bearish momentum

def evaluate_ema_crossover(ticker: str, bars: list[Bar], positions: dict | None = None) -> Signal:
    if len(bars) < 25:
        return Signal(ticker=ticker, action="HOLD", confidence=0.0, reason="Insufficient data")

    df = _bars_to_df(bars)

    ema_fast = ta.ema(df["close"], length=9)
    ema_slow = ta.ema(df["close"], length=21)

    if ema_fast is None or ema_slow is None:
        return Signal(ticker=ticker, action="HOLD", confidence=0.0, reason="EMA calculation failed")

    curr_fast = ema_fast.iloc[-1]
    curr_slow = ema_slow.iloc[-1]
    prev_fast = ema_fast.iloc[-2]
    prev_slow = ema_slow.iloc[-2]

    if pd.isna(curr_fast) or pd.isna(curr_slow) or pd.isna(prev_fast) or pd.isna(prev_slow):
        return Signal(ticker=ticker, action="HOLD", confidence=0.0, reason="EMA not ready")

    spread_pct = (curr_fast - curr_slow) / curr_slow * 100

    # Bullish crossover: fast crosses above slow
    if prev_fast <= prev_slow and curr_fast > curr_slow:
        return Signal(ticker=ticker, action="BUY", confidence=0.7,
                       reason=f"EMA 9/21 bullish crossover (spread {spread_pct:+.3f}%)")

    # Bearish crossover: fast crosses below slow
    if prev_fast >= prev_slow and curr_fast < curr_slow:
        return Signal(ticker=ticker, action="SELL", confidence=0.7,
                       reason=f"EMA 9/21 bearish crossover (spread {spread_pct:+.3f}%)")

    # Strong trend continuation
    if curr_fast > curr_slow and spread_pct > 0.1:
        return Signal(ticker=ticker, action="BUY", confidence=0.4,
                       reason=f"EMA bullish trend (spread {spread_pct:+.3f}%)")

    if curr_fast < curr_slow and spread_pct < -0.1:
        return Signal(ticker=ticker, action="SELL", confidence=0.4,
                       reason=f"EMA bearish trend (spread {spread_pct:+.3f}%)")

    return Signal(ticker=ticker, action="HOLD", confidence=0.0,
                   reason=f"EMA flat (spread {spread_pct:+.3f}%)")


# ---------------------------------------------------------------------------
# 3. Mean Reversion (Bollinger Band Bounce)
# ---------------------------------------------------------------------------
# Buy when price touches lower Bollinger Band (oversold)
# Sell when price touches upper Bollinger Band (overbought)
# Uses RSI as confirmation

def evaluate_mean_reversion(ticker: str, bars: list[Bar], positions: dict | None = None) -> Signal:
    if len(bars) < 25:
        return Signal(ticker=ticker, action="HOLD", confidence=0.0, reason="Insufficient data")

    df = _bars_to_df(bars)

    bbands = ta.bbands(df["close"], length=20, std=2)
    rsi = ta.rsi(df["close"], length=14)

    if bbands is None or rsi is None:
        return Signal(ticker=ticker, action="HOLD", confidence=0.0, reason="Indicator calculation failed")

    current_price = df["close"].iloc[-1]
    bb_lower = bbands.iloc[-1].iloc[0]
    bb_middle = bbands.iloc[-1].iloc[1]
    bb_upper = bbands.iloc[-1].iloc[2]
    current_rsi = rsi.iloc[-1]

    if pd.isna(bb_lower) or pd.isna(current_rsi):
        return Signal(ticker=ticker, action="HOLD", confidence=0.0, reason="Indicators not ready")

    bb_range = bb_upper - bb_lower
    if bb_range <= 0:
        return Signal(ticker=ticker, action="HOLD", confidence=0.0, reason="BB range zero")

    bb_position = (current_price - bb_lower) / bb_range  # 0 = lower band, 1 = upper band

    # BUY: price at/below lower BB + RSI confirms oversold
    if bb_position < 0.1 and current_rsi < 40:
        confidence = 0.5 + (0.1 - bb_position) * 3 + (40 - current_rsi) / 100
        return Signal(ticker=ticker, action="BUY", confidence=min(confidence, 0.9),
                       reason=f"BB bounce: price at lower band ({bb_position:.0%}), RSI {current_rsi:.0f}")

    # SELL: price at/above upper BB + RSI confirms overbought
    if bb_position > 0.9 and current_rsi > 60:
        confidence = 0.5 + (bb_position - 0.9) * 3 + (current_rsi - 60) / 100
        return Signal(ticker=ticker, action="SELL", confidence=min(confidence, 0.9),
                       reason=f"BB rejection: price at upper band ({bb_position:.0%}), RSI {current_rsi:.0f}")

    # Price reverting toward middle
    if bb_position < 0.3 and current_rsi < 45:
        return Signal(ticker=ticker, action="BUY", confidence=0.4,
                       reason=f"Near lower BB ({bb_position:.0%}), RSI {current_rsi:.0f}")

    if bb_position > 0.7 and current_rsi > 55:
        return Signal(ticker=ticker, action="SELL", confidence=0.4,
                       reason=f"Near upper BB ({bb_position:.0%}), RSI {current_rsi:.0f}")

    return Signal(ticker=ticker, action="HOLD", confidence=0.0,
                   reason=f"BB mid-range ({bb_position:.0%}), RSI {current_rsi:.0f}")


# ---------------------------------------------------------------------------
# 4. Breakout (Volume Confirmed)
# ---------------------------------------------------------------------------
# Buy when price breaks above recent high with above-average volume
# Sell when price breaks below recent low with above-average volume

def evaluate_breakout(ticker: str, bars: list[Bar], positions: dict | None = None) -> Signal:
    if len(bars) < 30:
        return Signal(ticker=ticker, action="HOLD", confidence=0.0, reason="Insufficient data")

    df = _bars_to_df(bars)

    # Look at last 20 bars for range, current bar for breakout
    lookback = df.iloc[-21:-1]  # previous 20 bars (excluding current)
    current = df.iloc[-1]

    recent_high = lookback["high"].max()
    recent_low = lookback["low"].min()
    avg_volume = lookback["volume"].mean()

    current_price = current["close"]
    current_volume = current["volume"]

    # Volume confirmation: current volume should be above average
    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

    # Breakout above resistance
    if current_price > recent_high and volume_ratio > 1.2:
        breakout_pct = (current_price - recent_high) / recent_high * 100
        confidence = min(0.5 + volume_ratio / 5 + breakout_pct / 2, 0.9)
        return Signal(ticker=ticker, action="BUY", confidence=confidence,
                       reason=f"Breakout above {recent_high:.2f} (+{breakout_pct:.2f}%), vol {volume_ratio:.1f}x")

    # Breakdown below support
    if current_price < recent_low and volume_ratio > 1.2:
        breakdown_pct = (recent_low - current_price) / recent_low * 100
        confidence = min(0.5 + volume_ratio / 5 + breakdown_pct / 2, 0.9)
        return Signal(ticker=ticker, action="SELL", confidence=confidence,
                       reason=f"Breakdown below {recent_low:.2f} (-{breakdown_pct:.2f}%), vol {volume_ratio:.1f}x")

    # Near resistance/support with volume building
    range_size = recent_high - recent_low
    if range_size > 0:
        range_position = (current_price - recent_low) / range_size

        if range_position > 0.9 and volume_ratio > 1.0:
            return Signal(ticker=ticker, action="BUY", confidence=0.4,
                           reason=f"Testing resistance {recent_high:.2f}, vol {volume_ratio:.1f}x")

        if range_position < 0.1 and volume_ratio > 1.0:
            return Signal(ticker=ticker, action="SELL", confidence=0.4,
                           reason=f"Testing support {recent_low:.2f}, vol {volume_ratio:.1f}x")

    return Signal(ticker=ticker, action="HOLD", confidence=0.0,
                   reason=f"In range [{recent_low:.2f}-{recent_high:.2f}], vol {volume_ratio:.1f}x")


# ---------------------------------------------------------------------------
# 5. Opening Range Breakout (ORB)
# ---------------------------------------------------------------------------
# Define the "opening range" as the high/low of the first 30 bars (~30 min)
# Buy when price breaks above the opening range high
# Sell when price breaks below the opening range low

def evaluate_orb(ticker: str, bars: list[Bar], positions: dict | None = None) -> Signal:
    if len(bars) < 35:
        return Signal(ticker=ticker, action="HOLD", confidence=0.0, reason="Insufficient data")

    # First 30 bars define the opening range
    opening_bars = bars[:30]
    or_high = max(b.high for b in opening_bars)
    or_low = min(b.low for b in opening_bars)
    or_mid = (or_high + or_low) / 2

    current_bar = bars[-1]
    prev_bar = bars[-2]
    current_price = current_bar.close

    # Only trade after the opening range is established (bar 30+)
    if len(bars) < 31:
        return Signal(ticker=ticker, action="HOLD", confidence=0.0,
                       reason=f"Building opening range [{or_low:.2f}-{or_high:.2f}]")

    or_range = or_high - or_low
    if or_range <= 0:
        return Signal(ticker=ticker, action="HOLD", confidence=0.0, reason="No opening range")

    has_position = ticker in (positions or {})

    # Breakout above opening range high
    if prev_bar.close <= or_high and current_price > or_high:
        breakout_pct = (current_price - or_high) / or_high * 100
        return Signal(ticker=ticker, action="BUY", confidence=0.7,
                       reason=f"ORB breakout above {or_high:.2f} (+{breakout_pct:.2f}%)")

    # Breakdown below opening range low
    if prev_bar.close >= or_low and current_price < or_low:
        breakdown_pct = (or_low - current_price) / or_low * 100
        return Signal(ticker=ticker, action="SELL", confidence=0.7,
                       reason=f"ORB breakdown below {or_low:.2f} (-{breakdown_pct:.2f}%)")

    # Already above range — stay long or take profit near 2x range
    if current_price > or_high:
        profit_target = or_high + or_range  # 1:1 risk/reward
        if current_price > profit_target and has_position:
            return Signal(ticker=ticker, action="SELL", confidence=0.6,
                           reason=f"ORB profit target hit ({current_price:.2f} > {profit_target:.2f})")
        return Signal(ticker=ticker, action="HOLD", confidence=0.0,
                       reason=f"Above OR, target {profit_target:.2f}")

    # Already below range — stay short or cover near 2x range
    if current_price < or_low:
        cover_target = or_low - or_range
        if current_price < cover_target and has_position:
            return Signal(ticker=ticker, action="BUY", confidence=0.6,
                           reason=f"ORB cover target hit ({current_price:.2f} < {cover_target:.2f})")
        return Signal(ticker=ticker, action="HOLD", confidence=0.0,
                       reason=f"Below OR, target {cover_target:.2f}")

    return Signal(ticker=ticker, action="HOLD", confidence=0.0,
                   reason=f"Inside opening range [{or_low:.2f}-{or_high:.2f}]")


# Registry of all strategies
STRATEGY_REGISTRY = {
    "vwap": evaluate_vwap,
    "ema_crossover": evaluate_ema_crossover,
    "mean_reversion": evaluate_mean_reversion,
    "breakout": evaluate_breakout,
    "orb": evaluate_orb,
}
