"""
Backtest mode: replays a historical trading day through the analysis/strategy/execution
pipeline, showing results in the CLI as if it were happening live.

Usage: stock-trader --backtest 2026-03-14
"""
import logging
import time
from datetime import datetime

from ib_insync import IB, Stock

from stock_trader.config import Config
from stock_trader.analysis import compute_indicators
from stock_trader.strategy import evaluate
from stock_trader.strategy_ai import evaluate_ai
from stock_trader.execution import ExecutionManager
from stock_trader.models import Bar, Signal, Trade

logger = logging.getLogger(__name__)


class BacktestEngine:
    """Replays historical bars through the strategy engine."""

    def __init__(
        self,
        config: Config,
        date: str,
        speed: float = 0.1,
        strategy: str = "classic",
    ):
        self.config = config
        self.date = date
        self.speed = speed  # seconds between bar replays
        self.strategy_mode = strategy

        self.execution = ExecutionManager(
            config=config.risk,
            place_order_fn=None,  # no real orders in backtest
        )

        self.on_signal = None
        self.on_trade = None

        self.ib = IB()
        self._bars: dict[str, list[Bar]] = {}
        self._all_bars: dict[str, list[Bar]] = {}
        self._current_index: dict[str, int] = {}
        self._replay_done = False
        self._connected = False
        self._bar_count = 0
        self._total_bars = 0

    def start(self) -> None:
        """Connect to IBKR and fetch historical data for the backtest date."""
        logger.info("Backtest: connecting to IBKR to fetch historical data for %s", self.date)
        self.ib.connect(
            host=self.config.ibkr.host,
            port=self.config.ibkr.port,
            clientId=self.config.ibkr.client_id,
        )
        self.ib.reqMarketDataType(3)
        self._connected = True

        for ticker in self.config.watchlist:
            print(f"  Fetching {ticker}...", end=" ", flush=True)
            contract = Stock(ticker, "SMART", "USD")
            self.ib.qualifyContracts(contract)

            # Retry up to 3 times — IBKR sometimes rejects first requests
            ib_bars = None
            for attempt in range(3):
                ib_bars = self.ib.reqHistoricalData(
                    contract,
                    endDateTime=f"{self.date.replace('-', '')} 23:59:59 US/Eastern",
                    durationStr="1 D",
                    barSizeSetting="1 min",
                    whatToShow="TRADES",
                    useRTH=True,
                    formatDate=1,
                )
                if ib_bars:
                    break
                if attempt < 2:
                    print(f"retry {attempt + 2}...", end=" ", flush=True)
                    self.ib.sleep(2)

            if ib_bars:
                self._all_bars[ticker] = [
                    Bar(
                        timestamp=datetime.fromisoformat(str(b.date)),
                        open=b.open,
                        high=b.high,
                        low=b.low,
                        close=b.close,
                        volume=int(b.volume),
                    )
                    for b in ib_bars
                ]
                print(f"{len(self._all_bars[ticker])} bars")
            else:
                print("no data!")
                self._all_bars[ticker] = []

            self._bars[ticker] = []
            self._current_index[ticker] = 0

        # Disconnect from IBKR — we don't need it during replay
        self.ib.disconnect()
        self._connected = False

        total_loaded = sum(len(bars) for bars in self._all_bars.values())
        if total_loaded == 0:
            print(f"\nNo data loaded for {self.date}. Possible reasons:")
            print(f"  - Markets were closed on that date (weekend/holiday)")
            print(f"  - IBKR 'different IP' error — wait a minute and try again")
            print(f"  - Date is in the future")
            raise SystemExit(1)

        self._total_bars = max(len(bars) for bars in self._all_bars.values()) if self._all_bars else 0
        logger.info("Backtest: ready to replay %d bars", self._total_bars)

    def stop(self) -> None:
        if self._connected and self.ib.isConnected():
            self.ib.disconnect()

    def sleep(self, seconds: float = 0.1) -> None:
        """Advance the replay by one bar for each ticker."""
        if self._replay_done:
            time.sleep(seconds)
            return

        time.sleep(self.speed)

        any_advanced = False
        for ticker in self.config.watchlist:
            idx = self._current_index.get(ticker, 0)
            all_bars = self._all_bars.get(ticker, [])

            if idx < len(all_bars):
                self._bars[ticker] = all_bars[:idx + 1]
                self._current_index[ticker] = idx + 1
                any_advanced = True
                self._bar_count = max(self._bar_count, idx + 1)

                # Run the pipeline
                self._process_bar(ticker)

        if not any_advanced:
            self._replay_done = True
            logger.info("Backtest complete. Final P/L: $%.2f", self.execution.daily_pnl)

    def _process_bar(self, ticker: str) -> None:
        bars = self._bars[ticker]
        if len(bars) < 2:
            return

        indicators = compute_indicators(ticker, bars, self.config.analysis)
        if self.strategy_mode == "ai":
            signal = evaluate_ai(indicators, bars, self.config.strategy, self.execution.positions)
        else:
            signal = evaluate(indicators, self.config.strategy)

        if self.on_signal:
            self.on_signal(signal)

        # Check stop losses
        current_prices = {
            t: self._bars[t][-1].close
            for t in self.execution.positions
            if self._bars.get(t)
        }
        stop_signals = self.execution.check_stop_losses(
            current_prices, self.config.strategy.stop_loss_pct
        )
        for stop_signal in stop_signals:
            price = current_prices[stop_signal.ticker]
            trade = self.execution.process_signal(stop_signal, price)
            if trade and self.on_trade:
                self.on_trade(trade)

        if signal.is_actionable(self.config.strategy.confidence_threshold):
            price = bars[-1].close
            trade = self.execution.process_signal(signal, price)
            if trade and self.on_trade:
                self.on_trade(trade)

    class _MarketDataProxy:
        """Minimal proxy so the CLI can read bars the same way."""
        def __init__(self, engine: "BacktestEngine"):
            self._engine = engine

        def get_bars(self, ticker: str) -> list[Bar]:
            return self._engine._bars.get(ticker, [])

        @property
        def ib(self):
            return self._engine.ib

    @property
    def market_data(self):
        return self._MarketDataProxy(self)

    def add_ticker(self, ticker: str) -> None:
        pass  # Not supported in backtest

    def remove_ticker(self, ticker: str) -> None:
        pass  # Not supported in backtest

    def pause(self) -> None:
        self.execution.is_paused = True

    def resume(self) -> None:
        self.execution.is_paused = False
