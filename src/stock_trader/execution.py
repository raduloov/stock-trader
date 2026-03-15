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
        return trade

    def _handle_sell(self, signal: Signal, price: float) -> Trade | None:
        if signal.ticker not in self.positions:
            return None

        position = self.positions[signal.ticker]

        # Place order via IBKR if callback provided
        if self.place_order_fn is not None:
            self.place_order_fn(signal.ticker, "SELL", position.quantity, price)

        # Calculate P/L
        pnl = position.unrealized_pnl(price)
        self.daily_pnl += pnl

        trade = Trade(
            timestamp=datetime.now(),
            ticker=signal.ticker,
            action="SELL",
            quantity=position.quantity,
            price=price,
            reason=signal.reason,
        )
        self.trades.append(trade)

        # Remove position
        del self.positions[signal.ticker]

        # Check daily loss limit
        if self.daily_pnl <= self.config.daily_loss_limit:
            self.is_halted = True

        return trade

    def check_stop_losses(self, prices: dict[str, float], stop_loss_pct: float) -> list[Signal]:
        """Check all positions for stop-loss hits. Returns sell signals."""
        signals = []
        for ticker, position in list(self.positions.items()):
            if ticker in prices:
                current = prices[ticker]
                loss_pct = (position.entry_price - current) / position.entry_price * 100
                if loss_pct >= stop_loss_pct:
                    signals.append(Signal(
                        ticker=ticker,
                        action="SELL",
                        confidence=1.0,
                        reason=f"Stop-loss triggered ({loss_pct:.1f}% loss)",
                    ))
        return signals
