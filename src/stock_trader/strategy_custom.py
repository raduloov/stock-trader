"""
Custom strategy: RSI + VWAP confirmation on 5-min bars.

BUY when: RSI <= 25 AND price > VWAP
SELL when: RSI >= 75 AND price < VWAP
Timeframe: 5 min (use MINUTE_5 resolution from Capital.com)
"""
import logging

import pandas as pd

from stock_trader.models import Bar, Signal

logger = logging.getLogger(__name__)


def evaluate_custom(ticker: str, bars: list[Bar], positions: dict | None = None) -> Signal:
    if len(bars) < 20:
        return Signal(ticker=ticker, action="HOLD", confidence=0.0, reason="Insufficient data")

    # Calculate RSI (14-period)
    closes = pd.Series([b.close for b in bars])
    delta = closes.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    current_rsi = rsi.iloc[-1]

    if pd.isna(current_rsi):
        return Signal(ticker=ticker, action="HOLD", confidence=0.0, reason="RSI not ready")

    # Calculate VWAP
    typical_price = pd.Series([(b.high + b.low + b.close) / 3 for b in bars])
    volume = pd.Series([b.volume for b in bars])
    cum_vol = volume.cumsum()
    cum_tp_vol = (typical_price * volume).cumsum()
    vwap = cum_tp_vol / cum_vol
    current_vwap = vwap.iloc[-1]
    current_price = bars[-1].close

    if pd.isna(current_vwap) or current_vwap == 0:
        return Signal(ticker=ticker, action="HOLD", confidence=0.0, reason="VWAP not ready")

    price_vs_vwap = (current_price - current_vwap) / current_vwap * 100
    price_above_vwap = current_price > current_vwap
    price_below_vwap = current_price < current_vwap
    has_position = ticker in (positions or {})

    # BUY: RSI <= 25 AND price > VWAP
    if current_rsi <= 25 and price_above_vwap:
        confidence = min(0.5 + (25 - current_rsi) / 25 + price_vs_vwap / 2, 1.0)
        return Signal(
            ticker=ticker,
            action="BUY",
            confidence=confidence,
            reason=f"RSI oversold ({current_rsi:.0f}) + above VWAP ({price_vs_vwap:+.2f}%)",
        )

    # SELL: RSI >= 75 AND price < VWAP
    if current_rsi >= 75 and price_below_vwap:
        confidence = min(0.5 + (current_rsi - 75) / 25 + abs(price_vs_vwap) / 2, 1.0)
        return Signal(
            ticker=ticker,
            action="SELL",
            confidence=confidence,
            reason=f"RSI overbought ({current_rsi:.0f}) + below VWAP ({price_vs_vwap:+.2f}%)",
        )

    # Info for display
    status = f"RSI={current_rsi:.0f}, VWAP={price_vs_vwap:+.2f}%"
    if current_rsi <= 35:
        status += " (approaching buy zone)"
    elif current_rsi >= 65:
        status += " (approaching sell zone)"
    return Signal(ticker=ticker, action="HOLD", confidence=0.0, reason=status)
