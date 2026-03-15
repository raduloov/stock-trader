import logging
from typing import Callable

from stock_trader.config import Config, save_config
from stock_trader.market_data import MarketDataManager
from stock_trader.analysis import compute_indicators
from stock_trader.strategy import evaluate
from stock_trader.execution import ExecutionManager
from stock_trader.models import Bar, Signal, Trade

logger = logging.getLogger(__name__)


class Engine:
    def __init__(
        self,
        config: Config,
        on_signal: Callable[[Signal], None] | None = None,
        on_trade: Callable[[Trade], None] | None = None,
    ):
        self.config = config
        self.on_signal = on_signal
        self.on_trade = on_trade

        self.execution = ExecutionManager(
            config=config.risk,
            place_order_fn=self._place_ibkr_order,
        )

        self.market_data = MarketDataManager(
            ibkr_config=config.ibkr,
            market_config=config.market_data,
            on_bar=self._on_bar,
        )

    def start(self) -> None:
        logger.info("Connecting to IBKR at %s:%d", self.config.ibkr.host, self.config.ibkr.port)
        self.market_data.connect()

        # TEMPORARY: Use polling mode until real-time market data subscriptions
        # are set up in IBKR. Once you have real-time permissions, remove this
        # line to use streaming mode instead.
        self.market_data.enable_polling_mode()

        for ticker in self.config.watchlist:
            logger.info("Subscribing to %s", ticker)
            self.market_data.subscribe(ticker)

        logger.info("Engine started. %s",
                     "Polling historical data." if self.market_data._use_polling
                     else "Streaming market data.")

    def stop(self) -> None:
        logger.info("Shutting down engine.")
        self.market_data.disconnect()

    def run_forever(self) -> None:
        """Block and process events until interrupted."""
        try:
            self.market_data.run()
        except KeyboardInterrupt:
            self.stop()

    def sleep(self, seconds: float = 0.1) -> None:
        """Process pending events (non-blocking tick)."""
        self.market_data.sleep(seconds)
        # Poll for new data if in polling mode
        self.market_data.poll_updates()

    def _on_bar(self, ticker: str, bars: list[Bar]) -> None:
        """Called when a new bar arrives for a ticker."""
        # 1. Compute indicators
        indicators = compute_indicators(ticker, bars, self.config.analysis)

        # 2. Evaluate strategy
        signal = evaluate(indicators, self.config.strategy)

        if self.on_signal:
            self.on_signal(signal)

        # 3. Check stop losses
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

        # 4. Execute if actionable
        if signal.is_actionable(self.config.strategy.confidence_threshold):
            price = bars[-1].close
            trade = self.execution.process_signal(signal, price)
            if trade and self.on_trade:
                self.on_trade(trade)

    def _place_ibkr_order(self, ticker: str, action: str, quantity: int, price: float) -> None:
        """Place an order via IBKR. For paper trading, market orders are fine."""
        from ib_insync import Stock, MarketOrder
        contract = Stock(ticker, "SMART", "USD")
        self.market_data.ib.qualifyContracts(contract)
        order = MarketOrder(action, quantity)
        self.market_data.ib.placeOrder(contract, order)
        logger.info("Placed %s order: %s %d @ market", action, ticker, quantity)

    def add_ticker(self, ticker: str) -> None:
        if ticker not in self.config.watchlist:
            self.config.watchlist.append(ticker)
            self.market_data.subscribe(ticker)
            save_config(self.config)
            logger.info("Added %s to watchlist", ticker)

    def remove_ticker(self, ticker: str) -> None:
        if ticker in self.config.watchlist:
            self.config.watchlist.remove(ticker)
            self.market_data.unsubscribe(ticker)
            save_config(self.config)
            logger.info("Removed %s from watchlist", ticker)

    def pause(self) -> None:
        self.execution.is_paused = True
        logger.info("Trading paused")

    def resume(self) -> None:
        self.execution.is_paused = False
        logger.info("Trading resumed")
