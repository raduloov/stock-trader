"""
Engine using Capital.com for CFD trading.
Drop-in replacement for the IBKR engine.
"""
import logging
from typing import Callable

from stock_trader.capital_com import CapitalComClient, CapitalComMarketData
from stock_trader.config import Config, save_config
from stock_trader.analysis import compute_indicators
from stock_trader.strategy import evaluate
from stock_trader.strategy_custom import evaluate_custom
from stock_trader.execution import ExecutionManager
from stock_trader.models import Bar, Signal, Trade

logger = logging.getLogger(__name__)


class CapitalEngine:
    def __init__(
        self,
        config: Config,
        client: CapitalComClient,
        on_signal: Callable[[Signal], None] | None = None,
        on_trade: Callable[[Trade], None] | None = None,
        strategy: str = "classic",
    ):
        self.config = config
        self.on_signal = on_signal
        self.on_trade = on_trade
        self.strategy_mode = strategy

        self.execution = ExecutionManager(
            config=config.risk,
            place_order_fn=self._place_order,
        )

        self.market_data = CapitalComMarketData(
            client=client,
            history_window=config.market_data.history_window,
            poll_interval=config.market_data.poll_interval,
            on_bar=self._on_bar,
        )

    def start(self) -> None:
        logger.info("Connecting to Capital.com")
        self.market_data.connect()

        for ticker in self.config.watchlist:
            logger.info("Subscribing to %s", ticker)
            self.market_data.subscribe(ticker)

        logger.info("Engine started. Polling market data.")

    def stop(self) -> None:
        logger.info("Shutting down engine.")
        self.market_data.disconnect()

    def sleep(self, seconds: float = 0.1) -> None:
        self.market_data.sleep(seconds)
        self.market_data.poll_updates()

    def _on_bar(self, ticker: str, bars: list[Bar]) -> None:
        indicators = compute_indicators(ticker, bars, self.config.analysis)

        if self.strategy_mode == "ai":
            from stock_trader.strategy_ai import evaluate_ai
            signal = evaluate_ai(indicators, bars, self.config.strategy, self.execution.positions)
        elif self.strategy_mode == "custom":
            signal = evaluate_custom(ticker, bars, self.execution.positions)
        else:
            signal = evaluate(indicators, self.config.strategy)

        logger.info("Signal %s: %s (%.0f%%) RSI=%.1f — %s",
                     ticker, signal.action, signal.confidence * 100,
                     indicators.rsi or 0, signal.reason)

        if self.on_signal:
            self.on_signal(signal)

        # Check stop losses
        current_prices = {
            t: self.market_data.get_bars(t)[-1].close
            for t in self.execution.positions
            if self.market_data.get_bars(t)
        }
        stop_signals = self.execution.check_stop_losses(
            current_prices, self.config.strategy.stop_loss_pct
        )
        for stop_signal in stop_signals:
            price = current_prices[stop_signal.ticker]
            trade = self.execution.process_signal(stop_signal, price)
            if trade and self.on_trade:
                self.on_trade(trade)

        is_act = signal.is_actionable(self.config.strategy.confidence_threshold)
        logger.info("Actionable check: %s %s conf=%.2f thresh=%.2f result=%s",
                     ticker, signal.action, signal.confidence, self.config.strategy.confidence_threshold, is_act)
        if is_act:
            price = bars[-1].close
            logger.info("Executing %s for %s @ %.2f",
                        signal.action, ticker, price)
            trade = self.execution.process_signal(signal, price)
            if trade:
                logger.info("Trade executed: %s %s %d @ %.2f", trade.action, trade.ticker, trade.quantity, trade.price)
                if self.on_trade:
                    self.on_trade(trade)
            else:
                logger.info("Trade rejected (risk limits or already in position)")

    def _place_order(self, ticker: str, action: str, quantity: int, price: float) -> None:
        """Place an order on Capital.com."""
        epic = self.market_data.epics.get(ticker)
        if not epic:
            logger.error("No epic found for %s, cannot place order", ticker)
            return

        try:
            direction = "BUY" if action == "BUY" else "SELL"
            result = self.market_data.client.open_position(
                epic=epic,
                direction=direction,
                size=quantity,
            )
            deal_ref = result.get("dealReference", "unknown")
            logger.info("Placed %s order on Capital.com: %s %d x %s (ref: %s)",
                        action, ticker, quantity, epic, deal_ref)
        except Exception as e:
            logger.error("Failed to place order for %s: %s", ticker, e)

    def add_ticker(self, ticker: str) -> None:
        if ticker not in self.config.watchlist:
            from stock_trader.config import TickerConfig
            self.config.tickers.append(TickerConfig(symbol=ticker))
            self.market_data.subscribe(ticker)
            save_config(self.config)
            logger.info("Added %s to watchlist", ticker)

    def remove_ticker(self, ticker: str) -> None:
        if ticker in self.config.watchlist:
            self.config.tickers = [t for t in self.config.tickers if t.symbol != ticker]
            self.market_data.unsubscribe(ticker)
            save_config(self.config)
            logger.info("Removed %s from watchlist", ticker)

    def pause(self) -> None:
        self.execution.is_paused = True
        logger.info("Trading paused")

    def resume(self) -> None:
        self.execution.is_paused = False
        logger.info("Trading resumed")
