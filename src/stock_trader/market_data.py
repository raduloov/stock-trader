import logging
import time
from collections import defaultdict
from datetime import datetime
from typing import Callable

from ib_insync import IB, Stock, RealTimeBarList

from stock_trader.config import IbkrConfig, MarketDataConfig
from stock_trader.models import Bar

logger = logging.getLogger(__name__)


class MarketDataManager:
    def __init__(
        self,
        ibkr_config: IbkrConfig,
        market_config: MarketDataConfig,
        on_bar: Callable[[str, list[Bar]], None] | None = None,
    ):
        self.ibkr_config = ibkr_config
        self.market_config = market_config
        self.on_bar = on_bar
        self.ib = IB()
        self.bars: dict[str, list[Bar]] = defaultdict(list)
        self._contracts: dict[str, Stock] = {}
        self._subscriptions: dict[str, RealTimeBarList] = {}
        self._use_polling = False
        self._last_poll: float = 0
        self._poll_interval = market_config.poll_interval

    def connect(self) -> None:
        self.ib.connect(
            host=self.ibkr_config.host,
            port=self.ibkr_config.port,
            clientId=self.ibkr_config.client_id,
        )
        # Request delayed market data (free, 15-min delay) as fallback
        self.ib.reqMarketDataType(3)

    def disconnect(self) -> None:
        if self.ib.isConnected():
            for bars_list in self._subscriptions.values():
                try:
                    self.ib.cancelRealTimeBars(bars_list)
                except ConnectionError:
                    pass
            self.ib.disconnect()
        self._subscriptions.clear()

    def subscribe(self, ticker: str) -> None:
        contract = Stock(ticker, "SMART", "USD")
        self.ib.qualifyContracts(contract)
        self._contracts[ticker] = contract

        if self._use_polling:
            self._fetch_historical(ticker)
        else:
            try:
                rt_bars = self.ib.reqRealTimeBars(
                    contract,
                    barSize=5,
                    whatToShow="MIDPOINT",
                    useRTH=True,
                )
                rt_bars.updateEvent += lambda bars, has_new: self._on_realtime_bar(ticker, bars, has_new)
                self._subscriptions[ticker] = rt_bars
            except Exception as e:
                logger.warning("Real-time bars failed for %s: %s. Using polling mode.", ticker, e)
                self._use_polling = True
                self._fetch_historical(ticker)

    def subscribe_polling(self, ticker: str) -> None:
        """Subscribe using historical data polling only."""
        contract = Stock(ticker, "SMART", "USD")
        self.ib.qualifyContracts(contract)
        self._contracts[ticker] = contract
        self._use_polling = True
        self._fetch_historical(ticker)

    def unsubscribe(self, ticker: str) -> None:
        if ticker in self._subscriptions:
            try:
                self.ib.cancelRealTimeBars(self._subscriptions[ticker])
            except ConnectionError:
                pass
            del self._subscriptions[ticker]
        self._contracts.pop(ticker, None)

    def _fetch_historical(self, ticker: str) -> None:
        """Fetch historical bars for a ticker. Works with delayed data and outside market hours."""
        contract = self._contracts.get(ticker)
        if not contract:
            return

        try:
            ib_bars = self.ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr=f"{self.market_config.history_window * 5} S",
                barSizeSetting="5 secs",
                whatToShow="MIDPOINT",
                useRTH=True,
                formatDate=1,
            )

            if not ib_bars:
                # Try TRADES instead of MIDPOINT (works for some data types)
                ib_bars = self.ib.reqHistoricalData(
                    contract,
                    endDateTime="",
                    durationStr="1 D",
                    barSizeSetting="1 min",
                    whatToShow="TRADES",
                    useRTH=True,
                    formatDate=1,
                )

            if ib_bars:
                self.bars[ticker] = [
                    Bar(
                        timestamp=datetime.fromisoformat(str(b.date)) if hasattr(b.date, '__str__') else datetime.now(),
                        open=b.open,
                        high=b.high,
                        low=b.low,
                        close=b.close,
                        volume=int(b.volume),
                    )
                    for b in ib_bars[-self.market_config.history_window:]
                ]
                logger.info("Loaded %d historical bars for %s", len(self.bars[ticker]), ticker)

                if self.on_bar:
                    self.on_bar(ticker, self.bars[ticker])
            else:
                logger.warning("No historical data available for %s", ticker)

        except Exception as e:
            logger.error("Failed to fetch historical data for %s: %s", ticker, e)

    def poll_updates(self) -> None:
        """Poll for new historical data. Call this periodically from the engine."""
        if not self._use_polling:
            return

        now = time.time()
        if now - self._last_poll < self._poll_interval:
            return

        self._last_poll = now
        for ticker in list(self._contracts.keys()):
            self._fetch_historical(ticker)

    def enable_polling_mode(self) -> None:
        """
        TEMPORARY: Switch to polling mode because real-time market data
        subscriptions are not available. Once you have real-time data
        permissions from IBKR, remove this and use streaming mode instead.
        See: IBKR Account Management > Settings > Market Data Subscriptions
        """
        logger.info("Switching to polling mode (historical data)")
        self._use_polling = True
        # Cancel any active real-time subscriptions
        for bars_list in self._subscriptions.values():
            try:
                self.ib.cancelRealTimeBars(bars_list)
            except ConnectionError:
                pass
        self._subscriptions.clear()

    def _on_realtime_bar(self, ticker: str, bars_list: RealTimeBarList, has_new: bool) -> None:
        if not has_new or not bars_list:
            return

        ib_bar = bars_list[-1]
        bar = Bar(
            timestamp=datetime.fromtimestamp(ib_bar.time.timestamp()) if hasattr(ib_bar.time, 'timestamp') else datetime.now(),
            open=ib_bar.open_,
            high=ib_bar.high,
            low=ib_bar.low,
            close=ib_bar.close,
            volume=int(ib_bar.volume),
        )

        self.bars[ticker].append(bar)

        # Trim to history window
        max_bars = self.market_config.history_window
        if len(self.bars[ticker]) > max_bars:
            self.bars[ticker] = self.bars[ticker][-max_bars:]

        if self.on_bar:
            self.on_bar(ticker, self.bars[ticker])

    def get_bars(self, ticker: str) -> list[Bar]:
        return self.bars.get(ticker, [])

    def run(self) -> None:
        """Run the ib_insync event loop. Blocks until disconnect."""
        self.ib.run()

    def sleep(self, seconds: float = 0) -> None:
        """Process pending events."""
        self.ib.sleep(seconds)
