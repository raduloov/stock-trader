"""
Bulk backtester: runs multiple strategies across multiple dates,
collects results, and outputs a comparison summary.

Usage: stock-trader --bulk-test --from 2026-02-14 --to 2026-03-14
"""
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ib_insync import IB, Stock

from stock_trader.analysis import compute_indicators
from stock_trader.config import Config, StrategyConfig, RiskConfig, TickerConfig
from stock_trader.execution import ExecutionManager
from stock_trader.models import Bar, Signal
from stock_trader.strategy import evaluate
from stock_trader.strategies import STRATEGY_REGISTRY

logger = logging.getLogger(__name__)


STRATEGIES = {
    "Conservative": StrategyConfig(
        confidence_threshold=0.6,
        rsi_oversold=30,
        rsi_overbought=70,
        stop_loss_pct=2.0,
    ),
    "Aggressive": StrategyConfig(
        confidence_threshold=0.3,
        rsi_oversold=45,
        rsi_overbought=55,
        stop_loss_pct=2.0,
    ),
    "Momentum": StrategyConfig(
        confidence_threshold=0.5,
        rsi_oversold=40,
        rsi_overbought=60,
        stop_loss_pct=1.0,
    ),
    "Wide": StrategyConfig(
        confidence_threshold=0.4,
        rsi_oversold=35,
        rsi_overbought=65,
        stop_loss_pct=3.0,
    ),
    "Scalper": StrategyConfig(
        confidence_threshold=0.25,
        rsi_oversold=48,
        rsi_overbought=52,
        stop_loss_pct=0.5,
    ),
    "Swing": StrategyConfig(
        confidence_threshold=0.5,
        rsi_oversold=35,
        rsi_overbought=65,
        stop_loss_pct=1.5,
    ),
    "TightStop": StrategyConfig(
        confidence_threshold=0.3,
        rsi_oversold=40,
        rsi_overbought=60,
        stop_loss_pct=0.3,
    ),
    "LooseStop": StrategyConfig(
        confidence_threshold=0.3,
        rsi_oversold=40,
        rsi_overbought=60,
        stop_loss_pct=5.0,
    ),
}


@dataclass
class DayResult:
    date: str
    pnl: float
    trades: int
    wins: int
    losses: int
    capital_used: float = 0.0  # max capital deployed at any point during the day


@dataclass
class StrategyResult:
    name: str
    days: list[DayResult] = field(default_factory=list)

    @property
    def total_pnl(self) -> float:
        return sum(d.pnl for d in self.days)

    @property
    def total_trades(self) -> int:
        return sum(d.trades for d in self.days)

    @property
    def total_wins(self) -> int:
        return sum(d.wins for d in self.days)

    @property
    def total_losses(self) -> int:
        return sum(d.losses for d in self.days)

    @property
    def win_rate(self) -> float:
        total = self.total_wins + self.total_losses
        return (self.total_wins / total * 100) if total > 0 else 0

    @property
    def avg_pnl_per_trade(self) -> float:
        return (self.total_pnl / self.total_trades) if self.total_trades > 0 else 0

    @property
    def max_drawdown(self) -> float:
        return min((d.pnl for d in self.days), default=0)

    @property
    def max_capital_used(self) -> float:
        return max((d.capital_used for d in self.days), default=0)

    @property
    def roi_pct(self) -> float:
        """Return on investment as percentage of max capital deployed."""
        if self.max_capital_used <= 0:
            return 0
        return self.total_pnl / self.max_capital_used * 100

    commission_rate: float = 1.0

    @property
    def total_commissions(self) -> float:
        return self.total_trades * self.commission_rate

    @property
    def profitable_days(self) -> int:
        return sum(1 for d in self.days if d.pnl > 0)


def _get_trading_dates(start: str, end: str) -> list[str]:
    """Generate weekday dates between start and end (inclusive)."""
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    dates = []
    current = start_dt
    while current <= end_dt:
        if current.weekday() < 5:  # Mon-Fri
            dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


def _fetch_all_data(
    config: Config,
    dates: list[str],
    broker: str = "ibkr",
) -> dict[str, dict[str, list[Bar]]]:
    """Fetch historical data for all tickers and dates. Returns {date: {ticker: [bars]}}."""
    if broker == "capital":
        return _fetch_all_data_capital(config, dates)
    return _fetch_all_data_ibkr(config, dates)


def _fetch_all_data_capital(
    config: Config,
    dates: list[str],
) -> dict[str, dict[str, list[Bar]]]:
    """Fetch historical data from Capital.com."""
    import os
    import time
    from stock_trader.capital_com import CapitalComClient

    print("Connecting to Capital.com to fetch historical data...")
    client = CapitalComClient(
        api_key=os.environ["CAPITAL_API_KEY"],
        email=os.environ["CAPITAL_EMAIL"],
        password=os.environ["CAPITAL_PASSWORD"],
        demo=True,
    )
    client.connect()

    # Resolve epics for all tickers
    epics = {}
    for ticker in config.watchlist:
        # Try exact match first
        try:
            test = client.get_prices(ticker, resolution="MINUTE", max_bars=1)
            if test:
                epics[ticker] = ticker
                continue
        except Exception:
            pass
        # Fall back to search
        markets = client.search_markets(ticker, limit=1)
        if markets:
            epics[ticker] = markets[0]["epic"]
            print(f"  Mapped {ticker} -> {epics[ticker]} ({markets[0].get('instrumentName', '')})")
        else:
            print(f"  Warning: could not find {ticker} on Capital.com")

    all_data: dict[str, dict[str, list[Bar]]] = {}
    total = len(dates) * len(config.watchlist)
    count = 0

    for date in dates:
        all_data[date] = {}

        for ticker in config.watchlist:
            count += 1
            print(f"\r  Fetching data: {count}/{total} ({ticker} {date})...", end="", flush=True)

            epic = epics.get(ticker)
            if not epic:
                all_data[date][ticker] = []
                continue

            try:
                date_from = f"{date}T00:00:00"
                date_to = f"{date}T23:59:59"
                raw_prices = client.get_prices_for_date(epic, date_from, date_to, resolution="MINUTE")

                if raw_prices:
                    all_data[date][ticker] = [
                        Bar(
                            timestamp=datetime.fromisoformat(p["snapshotTime"].replace("T", " ").split(".")[0]),
                            open=float(p.get("openPrice", {}).get("bid", 0)),
                            high=float(p.get("highPrice", {}).get("bid", 0)),
                            low=float(p.get("lowPrice", {}).get("bid", 0)),
                            close=float(p.get("closePrice", {}).get("bid", 0)),
                            volume=int(p.get("lastTradedVolume", 0)),
                        )
                        for p in raw_prices
                    ]
                else:
                    all_data[date][ticker] = []

                # Rate limit: Capital.com allows 10 req/sec
                time.sleep(0.15)

            except Exception as e:
                logger.error("Failed to fetch %s for %s: %s", ticker, date, e)
                all_data[date][ticker] = []

    print(f"\r  Fetched data for {len(dates)} dates, {len(config.watchlist)} tickers.     ")
    client.disconnect()
    return all_data


def _fetch_all_data_ibkr(
    config: Config,
    dates: list[str],
) -> dict[str, dict[str, list[Bar]]]:
    """Fetch historical data from IBKR."""
    print("Connecting to IBKR to fetch historical data...")
    ib = IB()
    ib.connect(
        host=config.ibkr.host,
        port=config.ibkr.port,
        clientId=config.ibkr.client_id,
    )
    ib.reqMarketDataType(3)

    contracts = {}
    for tc in config.tickers:
        contract = Stock(tc.symbol, tc.exchange, tc.currency)
        ib.qualifyContracts(contract)
        contracts[tc.symbol] = contract

    all_data: dict[str, dict[str, list[Bar]]] = {}
    total = len(dates) * len(config.watchlist)
    count = 0

    for date in dates:
        all_data[date] = {}
        date_fmt = date.replace("-", "")

        for ticker in config.watchlist:
            count += 1
            print(f"\r  Fetching data: {count}/{total} ({ticker} {date})...", end="", flush=True)

            contract = contracts.get(ticker)
            if not contract:
                continue

            ib_bars = None
            for attempt in range(3):
                ib_bars = ib.reqHistoricalData(
                    contract,
                    endDateTime=f"{date_fmt} 23:59:59 US/Eastern",
                    durationStr="1 D",
                    barSizeSetting="1 min",
                    whatToShow="TRADES",
                    useRTH=True,
                    formatDate=1,
                )
                if ib_bars:
                    break
                ib.sleep(1)

            if ib_bars:
                all_data[date][ticker] = [
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
            else:
                all_data[date][ticker] = []

    print(f"\r  Fetched data for {len(dates)} dates, {len(config.watchlist)} tickers.     ")
    ib.disconnect()
    return all_data


def _run_strategy_on_day(
    strategy_config: StrategyConfig,
    risk_config: RiskConfig,
    analysis_config,
    ticker_bars: dict[str, list[Bar]],
) -> DayResult:
    """Run a strategy on one day's data and return results."""
    execution = ExecutionManager(config=risk_config, place_order_fn=None)

    # Find max bar count across all tickers
    max_bars = max((len(bars) for bars in ticker_bars.values() if bars), default=0)
    tickers = [t for t, bars in ticker_bars.items() if bars]

    # Interleave: process bar i across ALL tickers before moving to bar i+1
    for i in range(20, max_bars):
        # Check stop losses first
        current_prices = {}
        for ticker in tickers:
            all_bars = ticker_bars[ticker]
            if i < len(all_bars):
                current_prices[ticker] = all_bars[i].close

        stop_signals = execution.check_stop_losses(
            current_prices, strategy_config.stop_loss_pct
        )
        for stop_signal in stop_signals:
            if stop_signal.ticker in current_prices:
                execution.process_signal(stop_signal, current_prices[stop_signal.ticker])

        # Then evaluate strategy for each ticker
        for ticker in tickers:
            all_bars = ticker_bars[ticker]
            if i >= len(all_bars):
                continue

            bars = all_bars[:i + 1]
            indicators = compute_indicators(ticker, bars, analysis_config)
            signal = evaluate(indicators, strategy_config)

            if signal.is_actionable(strategy_config.confidence_threshold):
                execution.process_signal(signal, bars[-1].close)

    # Force-close all open positions at end of day (day trading = no overnight)
    for ticker in list(execution.positions.keys()):
        pos = execution.positions[ticker]
        all_bars = ticker_bars.get(ticker, [])
        if not all_bars:
            continue
        close_price = all_bars[-1].close
        if pos.direction == "LONG":
            close_signal = Signal(ticker=ticker, action="SELL", confidence=1.0, reason="End of day close")
        else:
            close_signal = Signal(ticker=ticker, action="BUY", confidence=1.0, reason="End of day close")
        execution.process_signal(close_signal, close_price)

    # Count wins/losses from round-trip trades
    wins = 0
    losses = 0
    open_trades: dict[str, object] = {}
    for trade in execution.trades:
        if trade.action in ("BUY", "SHORT") and trade.ticker not in open_trades:
            open_trades[trade.ticker] = trade
        elif trade.ticker in open_trades:
            open_trade = open_trades.pop(trade.ticker)
            if open_trade.action == "BUY":
                pnl = (trade.price - open_trade.price) * trade.quantity
            else:  # SHORT closed by BUY
                pnl = (open_trade.price - trade.price) * trade.quantity
            if pnl > 0:
                wins += 1
            elif pnl < 0:
                losses += 1

    return DayResult(
        date="",
        pnl=execution.daily_pnl,
        trades=len(execution.trades),
        wins=wins,
        capital_used=execution.max_capital_used,
        losses=losses,
    )


def _run_bar_strategy_on_day(
    strategy_fn,
    risk_config: RiskConfig,
    ticker_bars: dict[str, list[Bar]],
    stop_loss_pct: float = 2.0,
) -> DayResult:
    """Run a bar-based strategy (VWAP, EMA crossover, etc.) on one day's data."""
    execution = ExecutionManager(config=risk_config, place_order_fn=None)

    max_bars = max((len(bars) for bars in ticker_bars.values() if bars), default=0)
    tickers = [t for t, bars in ticker_bars.items() if bars]

    for i in range(20, max_bars):
        # Check stop losses
        current_prices = {}
        for ticker in tickers:
            all_bars = ticker_bars[ticker]
            if i < len(all_bars):
                current_prices[ticker] = all_bars[i].close

        stop_signals = execution.check_stop_losses(current_prices, stop_loss_pct)
        for stop_signal in stop_signals:
            if stop_signal.ticker in current_prices:
                execution.process_signal(stop_signal, current_prices[stop_signal.ticker])

        # Evaluate strategy for each ticker
        for ticker in tickers:
            all_bars = ticker_bars[ticker]
            if i >= len(all_bars):
                continue

            bars = all_bars[:i + 1]
            signal = strategy_fn(ticker, bars, execution.positions)

            if signal.is_actionable(0.4):  # threshold for bar-based strategies
                execution.process_signal(signal, bars[-1].close)

    # Force-close at end of day
    for ticker in list(execution.positions.keys()):
        pos = execution.positions[ticker]
        all_bars = ticker_bars.get(ticker, [])
        if not all_bars:
            continue
        close_price = all_bars[-1].close
        if pos.direction == "LONG":
            close_signal = Signal(ticker=ticker, action="SELL", confidence=1.0, reason="End of day close")
        else:
            close_signal = Signal(ticker=ticker, action="BUY", confidence=1.0, reason="End of day close")
        execution.process_signal(close_signal, close_price)

    # Count wins/losses
    wins = 0
    losses = 0
    open_trades: dict[str, object] = {}
    for trade in execution.trades:
        if trade.action in ("BUY", "SHORT") and trade.ticker not in open_trades:
            open_trades[trade.ticker] = trade
        elif trade.ticker in open_trades:
            open_trade = open_trades.pop(trade.ticker)
            if open_trade.action == "BUY":
                pnl = (trade.price - open_trade.price) * trade.quantity
            else:
                pnl = (open_trade.price - trade.price) * trade.quantity
            if pnl > 0:
                wins += 1
            elif pnl < 0:
                losses += 1

    return DayResult(date="", pnl=execution.daily_pnl, trades=len(execution.trades), wins=wins, losses=losses, capital_used=execution.max_capital_used)


def run_bulk_backtest(config: Config, start_date: str, end_date: str, strategy_filter: list[str] | None = None, broker: str = "ibkr") -> list[StrategyResult]:
    """Run strategies across all dates and return results. Optionally filter by name."""
    dates = _get_trading_dates(start_date, end_date)
    if not dates:
        print("No trading days in the specified range.")
        return []

    # Build combined strategy list: indicator-based + bar-based
    all_strategies = {}
    for name, strat_config in STRATEGIES.items():
        all_strategies[name] = ("indicator", strat_config)
    for name, strat_fn in STRATEGY_REGISTRY.items():
        display_name = name.replace("_", " ").title()
        all_strategies[display_name] = ("bar", strat_fn)

    if strategy_filter:
        all_strategies = {k: v for k, v in all_strategies.items() if k in strategy_filter}
        if not all_strategies:
            available = list(STRATEGIES.keys()) + [n.replace("_", " ").title() for n in STRATEGY_REGISTRY.keys()]
            print(f"No matching strategies. Available: {', '.join(available)}")
            return []

    print(f"Bulk Backtest: {start_date} to {end_date} ({len(dates)} trading days)")
    print(f"Tickers: {', '.join(config.watchlist)}")
    print(f"Strategies: {', '.join(all_strategies.keys())}")
    print()

    # Fetch all data upfront
    all_data = _fetch_all_data(config, dates, broker=broker)

    valid_dates = [d for d in dates if any(all_data[d].get(t) for t in config.watchlist)]
    if not valid_dates:
        print("No data available for any trading day in range.")
        return []

    print(f"\nRunning {len(all_strategies)} strategies across {len(valid_dates)} days...")
    print()

    results = []
    for strat_name, (strat_type, strat) in all_strategies.items():
        print(f"  {strat_name}...", end=" ", flush=True)
        strat_result = StrategyResult(name=strat_name, commission_rate=config.risk.commission_per_trade)

        for date in valid_dates:
            ticker_bars = all_data[date]
            if strat_type == "indicator":
                day_result = _run_strategy_on_day(strat, config.risk, config.analysis, ticker_bars)
            else:
                day_result = _run_bar_strategy_on_day(strat, config.risk, ticker_bars)
            day_result.date = date
            strat_result.days.append(day_result)

        print(f"done ({strat_result.total_trades} trades, ${strat_result.total_pnl:+.2f})")
        results.append(strat_result)

    return results


def print_results(results: list[StrategyResult]) -> None:
    """Print a formatted comparison table."""
    if not results:
        return

    days_count = len(results[0].days) if results else 0

    print()
    print("=" * 110)
    comm_rate = results[0].commission_rate if results else 1.0
    print(f"  STRATEGY COMPARISON — {days_count} trading days (incl. ${comm_rate:.2f}/trade commission)")
    print("=" * 110)
    print()
    print(f"  {'Strategy':<16} {'P/L':>10} {'Commiss.':>10} {'Net P/L':>10} {'ROI%':>8} "
          f"{'WinRate':>8} {'Trades':>7} {'Capital':>10} {'Max DD':>10}")
    print(f"  {'-'*14:<16} {'-'*10:>10} {'-'*10:>10} {'-'*10:>10} {'-'*8:>8} "
          f"{'-'*8:>8} {'-'*7:>7} {'-'*10:>10} {'-'*10:>10}")

    # Sort by total P/L descending
    sorted_results = sorted(results, key=lambda r: r.total_pnl, reverse=True)

    for r in sorted_results:
        gross_pnl = r.total_pnl + r.total_commissions  # add back commissions to get gross
        comm_str = f"${r.total_commissions:,.0f}"
        net_str = f"${r.total_pnl:+.2f}"
        gross_str = f"${gross_pnl:+.2f}"
        roi_str = f"{r.roi_pct:+.1f}%"
        wr_str = f"{r.win_rate:.0f}%"
        cap_str = f"${r.max_capital_used:,.0f}"
        dd_str = f"${r.max_drawdown:+.2f}"

        print(f"  {r.name:<16} {gross_str:>10} {comm_str:>10} {net_str:>10} {roi_str:>8} "
              f"{wr_str:>8} {r.total_trades:>7} {cap_str:>10} {dd_str:>10}")

    print()

    # Best strategy
    best = sorted_results[0]
    print(f"  Best strategy: {best.name}")
    print(f"    Net P/L: ${best.total_pnl:+.2f} | ROI: {best.roi_pct:+.1f}% | "
          f"Capital used: ${best.max_capital_used:,.0f} | Win rate: {best.win_rate:.0f}%")
    print(f"    Commissions: ${best.total_commissions:,.2f} ({best.total_trades} trades x ${best.commission_rate:.2f})")
    print()

    # Per-day breakdown for best strategy
    print(f"  Daily P/L for {best.name}:")
    for day in best.days:
        bar = "+" * int(max(day.pnl, 0) / 5) if day.pnl >= 0 else "-" * int(abs(min(day.pnl, 0)) / 5)
        color_start = "\033[32m" if day.pnl >= 0 else "\033[31m"
        color_end = "\033[0m"
        print(f"    {day.date}  {color_start}${day.pnl:>+8.2f}{color_end}  "
              f"{day.trades:>2} trades  {bar}")
    print()
