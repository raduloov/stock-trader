from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass
class IndicatorResult:
    ticker: str
    sma: float | None = None
    ema: float | None = None
    rsi: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    close: float | None = None


@dataclass
class Signal:
    ticker: str
    action: str  # "BUY", "SELL", "HOLD"
    confidence: float
    reason: str

    def is_actionable(self, threshold: float) -> bool:
        return self.action in ("BUY", "SELL") and self.confidence >= threshold


@dataclass
class Position:
    ticker: str
    quantity: int
    entry_price: float
    direction: str = "LONG"  # "LONG" or "SHORT"

    def unrealized_pnl(self, current_price: float) -> float:
        if self.direction == "SHORT":
            return (self.entry_price - current_price) * self.quantity
        return (current_price - self.entry_price) * self.quantity


@dataclass
class Trade:
    timestamp: datetime
    ticker: str
    action: str  # "BUY", "SELL"
    quantity: int
    price: float
    reason: str
