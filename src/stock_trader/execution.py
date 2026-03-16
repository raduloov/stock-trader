import math
from datetime import datetime
from typing import Callable

from stock_trader.config import RiskConfig
from stock_trader.models import Signal, Position, Trade


class ExecutionManager:
    def __init__(
        self,
        config: RiskConfig,
        place_order_fn: Callable | None = None,
    ):
        self.config = config
        self.place_order_fn = place_order_fn
        self.positions: dict[str, Position] = {}
        self.trades: list[Trade] = []
        self.daily_pnl: float = 0.0
        self.is_halted: bool = False
        self.is_paused: bool = False

    def process_signal(self, signal: Signal, current_price: float) -> Trade | None:
        if self.is_halted or self.is_paused:
            return None

        if signal.action == "BUY":
            return self._handle_buy(signal, current_price)
        elif signal.action == "SELL":
            return self._handle_sell(signal, current_price)
        return None

    def _handle_buy(self, signal: Signal, price: float) -> Trade | None:
        # If we have a SHORT position, close it
        if signal.ticker in self.positions and self.positions[signal.ticker].direction == "SHORT":
            return self._close_position(signal, price)

        # No double entry
        if signal.ticker in self.positions:
            return None

        # Max positions check
        if len(self.positions) >= self.config.max_open_positions:
            return None

        # Calculate quantity
        quantity = math.floor(self.config.max_position_value / price)
        if quantity <= 0:
            return None

        # Place order via IBKR if callback provided
        if self.place_order_fn is not None:
            self.place_order_fn(signal.ticker, "BUY", quantity, price)

        # Track position
        self.positions[signal.ticker] = Position(
            ticker=signal.ticker,
            quantity=quantity,
            entry_price=price,
            direction="LONG",
        )

        trade = Trade(
            timestamp=datetime.now(),
            ticker=signal.ticker,
            action="BUY",
            quantity=quantity,
            price=price,
            reason=signal.reason,
        )
        self.trades.append(trade)
        self.daily_pnl -= self.config.commission_per_trade
        return trade

    def _handle_sell(self, signal: Signal, price: float) -> Trade | None:
        # If we have a LONG position, close it
        if signal.ticker in self.positions and self.positions[signal.ticker].direction == "LONG":
            return self._close_position(signal, price)

        # If no position, open a SHORT
        if signal.ticker not in self.positions:
            return self._open_short(signal, price)

        # Already short — no double entry
        return None

    def _close_position(self, signal: Signal, price: float) -> Trade | None:
        position = self.positions[signal.ticker]

        # Determine order action: close LONG = SELL, close SHORT = BUY
        order_action = "SELL" if position.direction == "LONG" else "BUY"

        if self.place_order_fn is not None:
            self.place_order_fn(signal.ticker, order_action, position.quantity, price)

        # Calculate P/L (minus commission)
        pnl = position.unrealized_pnl(price)
        self.daily_pnl += pnl - self.config.commission_per_trade

        trade = Trade(
            timestamp=datetime.now(),
            ticker=signal.ticker,
            action=order_action,
            quantity=position.quantity,
            price=price,
            reason=signal.reason,
        )
        self.trades.append(trade)

        del self.positions[signal.ticker]

        if self.daily_pnl <= self.config.daily_loss_limit:
            self.is_halted = True

        return trade

    def _open_short(self, signal: Signal, price: float) -> Trade | None:
        # Max positions check
        if len(self.positions) >= self.config.max_open_positions:
            return None

        quantity = math.floor(self.config.max_position_value / price)
        if quantity <= 0:
            return None

        if self.place_order_fn is not None:
            self.place_order_fn(signal.ticker, "SELL", quantity, price)

        self.positions[signal.ticker] = Position(
            ticker=signal.ticker,
            quantity=quantity,
            entry_price=price,
            direction="SHORT",
        )

        trade = Trade(
            timestamp=datetime.now(),
            ticker=signal.ticker,
            action="SHORT",
            quantity=quantity,
            price=price,
            reason=signal.reason,
        )
        self.trades.append(trade)
        self.daily_pnl -= self.config.commission_per_trade
        return trade

    def check_stop_losses(self, prices: dict[str, float], stop_loss_pct: float) -> list[Signal]:
        """Check all positions for stop-loss hits. Returns close signals."""
        signals = []
        for ticker, position in list(self.positions.items()):
            if ticker in prices:
                current = prices[ticker]
                if position.direction == "LONG":
                    loss_pct = (position.entry_price - current) / position.entry_price * 100
                    if loss_pct >= stop_loss_pct:
                        signals.append(Signal(
                            ticker=ticker,
                            action="SELL",
                            confidence=1.0,
                            reason=f"Stop-loss triggered ({loss_pct:.1f}% loss)",
                        ))
                else:  # SHORT
                    loss_pct = (current - position.entry_price) / position.entry_price * 100
                    if loss_pct >= stop_loss_pct:
                        signals.append(Signal(
                            ticker=ticker,
                            action="BUY",
                            confidence=1.0,
                            reason=f"Stop-loss triggered ({loss_pct:.1f}% loss on short)",
                        ))
        return signals
