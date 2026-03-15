from collections import defaultdict
from datetime import datetime
from typing import Callable

from ib_insync import IB, Stock, BarDataList, RealTimeBarList

from stock_trader.config import IbkrConfig, MarketDataConfig
from stock_trader.models import Bar


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
        self._subscriptions: dict[str, RealTimeBarList] = {}

    def connect(self) -> None:
        self.ib.connect(
            host=self.ibkr_config.host,
            port=self.ibkr_config.port,
            clientId=self.ibkr_config.client_id,
        )

    def disconnect(self) -> None:
        for bars_list in self._subscriptions.values():
            self.ib.cancelRealTimeBars(bars_list)
        self._subscriptions.clear()
        if self.ib.isConnected():
            self.ib.disconnect()

    def subscribe(self, ticker: str) -> None:
        contract = Stock(ticker, "SMART", "USD")
        self.ib.qualifyContracts(contract)
        rt_bars = self.ib.reqRealTimeBars(
            contract,
            barSize=5,
            whatToShow="MIDPOINT",
            useRTH=True,
        )
        rt_bars.updateEvent += lambda bars, has_new: self._on_realtime_bar(ticker, bars, has_new)
        self._subscriptions[ticker] = rt_bars

    def unsubscribe(self, ticker: str) -> None:
        if ticker in self._subscriptions:
            self.ib.cancelRealTimeBars(self._subscriptions[ticker])
            del self._subscriptions[ticker]

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
