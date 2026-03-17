"""
Custom strategy: RSI + VWAP with proper risk management.

Entry:
  BUY when: RSI <= 25 AND price > VWAP
  SELL when: RSI >= 75 AND price < VWAP

Risk management:
  Stop loss: below last 15-min candle low (longs) / above last 15-min candle high (shorts)
  Take profit: 1:2 RRR (2x the stop distance)
  Position size: risk 0.5% of account capital per trade

Timeframe: 5-min bars
"""
import logging
from dataclasses import dataclass

import pandas as pd

from stock_trader.models import Bar, Signal

logger = logging.getLogger(__name__)

# Account capital for position sizing
ACCOUNT_CAPITAL = 50000.0  # USD
RISK_PCT = 0.005  # 0.5% risk per trade


@dataclass
class TradeSetup:
    """Holds entry, stop, and take-profit levels for a trade."""
    direction: str  # "BUY" or "SELL"
    entry: float
    stop_loss: float
    take_profit: float
    size: float


# Store active setups so we can check TP/SL
_active_setups: dict[str, TradeSetup] = {}


def _get_15min_candle(bars: list[Bar]) -> tuple[float, float]:
    """Get the high and low of the last ~15 minutes (last 3 five-min bars)."""
    recent = bars[-3:] if len(bars) >= 3 else bars
    high = max(b.high for b in recent)
    low = min(b.low for b in recent)
    return high, low


def _calculate_position_size(entry: float, stop_loss: float, account_capital: float = ACCOUNT_CAPITAL) -> float:
    """Calculate position size based on 0.5% risk of account capital."""
    risk_amount = account_capital * RISK_PCT  # e.g., 21000 * 0.005 = $105
    stop_distance = abs(entry - stop_loss)
    if stop_distance <= 0:
        return 0
    size = risk_amount / stop_distance
    return round(size, 2)


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
    has_position = ticker in (positions or {})

    # Get 15-min candle levels for stop loss
    candle_high, candle_low = _get_15min_candle(bars)

    # Check take-profit / stop-loss for existing positions
    if has_position and ticker in _active_setups:
        setup = _active_setups[ticker]
        if setup.direction == "BUY":
            # Long: check if TP or SL hit
            if current_price >= setup.take_profit:
                del _active_setups[ticker]
                return Signal(ticker=ticker, action="SELL", confidence=1.0,
                              reason=f"TP hit ({current_price:.2f} >= {setup.take_profit:.2f})")
            if current_price <= setup.stop_loss:
                del _active_setups[ticker]
                return Signal(ticker=ticker, action="SELL", confidence=1.0,
                              reason=f"SL hit ({current_price:.2f} <= {setup.stop_loss:.2f})")
        elif setup.direction == "SELL":
            # Short: check if TP or SL hit
            if current_price <= setup.take_profit:
                del _active_setups[ticker]
                return Signal(ticker=ticker, action="BUY", confidence=1.0,
                              reason=f"TP hit ({current_price:.2f} <= {setup.take_profit:.2f})")
            if current_price >= setup.stop_loss:
                del _active_setups[ticker]
                return Signal(ticker=ticker, action="BUY", confidence=1.0,
                              reason=f"SL hit ({current_price:.2f} >= {setup.stop_loss:.2f})")

    # Don't open new positions if already in one
    if has_position:
        setup = _active_setups.get(ticker)
        if setup:
            return Signal(ticker=ticker, action="HOLD", confidence=0.0,
                          reason=f"In {setup.direction} | SL={setup.stop_loss:.2f} TP={setup.take_profit:.2f}")
        return Signal(ticker=ticker, action="HOLD", confidence=0.0, reason="In position")

    # BUY: RSI <= 25 AND price > VWAP
    if current_rsi <= 25 and current_price > current_vwap:
        stop_loss = candle_low  # stop below last 15-min low
        stop_distance = current_price - stop_loss
        if stop_distance <= 0:
            return Signal(ticker=ticker, action="HOLD", confidence=0.0, reason="Invalid stop distance")
        take_profit = current_price + (stop_distance * 2)  # 1:2 RRR
        size = _calculate_position_size(current_price, stop_loss)

        _active_setups[ticker] = TradeSetup(
            direction="BUY", entry=current_price,
            stop_loss=stop_loss, take_profit=take_profit, size=size,
        )

        confidence = min(0.5 + (25 - current_rsi) / 25 + price_vs_vwap / 2, 1.0)
        return Signal(
            ticker=ticker, action="BUY", confidence=confidence,
            reason=f"RSI={current_rsi:.0f} above VWAP | SL={stop_loss:.2f} TP={take_profit:.2f} Size={size}",
        )

    # SELL (short): RSI >= 75 AND price < VWAP
    if current_rsi >= 75 and current_price < current_vwap:
        stop_loss = candle_high  # stop above last 15-min high
        stop_distance = stop_loss - current_price
        if stop_distance <= 0:
            return Signal(ticker=ticker, action="HOLD", confidence=0.0, reason="Invalid stop distance")
        take_profit = current_price - (stop_distance * 2)  # 1:2 RRR
        size = _calculate_position_size(current_price, stop_loss)

        _active_setups[ticker] = TradeSetup(
            direction="SELL", entry=current_price,
            stop_loss=stop_loss, take_profit=take_profit, size=size,
        )

        confidence = min(0.5 + (current_rsi - 75) / 25 + abs(price_vs_vwap) / 2, 1.0)
        return Signal(
            ticker=ticker, action="SELL", confidence=confidence,
            reason=f"RSI={current_rsi:.0f} below VWAP | SL={stop_loss:.2f} TP={take_profit:.2f} Size={size}",
        )

    # Info for display
    status = f"RSI={current_rsi:.0f}, VWAP={price_vs_vwap:+.2f}%"
    if current_rsi <= 35:
        status += " (approaching buy zone)"
    elif current_rsi >= 65:
        status += " (approaching sell zone)"
    return Signal(ticker=ticker, action="HOLD", confidence=0.0, reason=status)
