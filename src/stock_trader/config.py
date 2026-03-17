from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class TickerConfig:
    """Config for a single ticker. US stocks only need the symbol."""
    symbol: str
    exchange: str = "SMART"
    currency: str = "USD"


@dataclass
class IbkrConfig:
    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 1


@dataclass
class MarketDataConfig:
    bar_size: str = "5 secs"
    history_window: int = 100
    poll_interval: int = 30  # seconds between polls (polling mode only)


@dataclass
class AnalysisConfig:
    sma_period: int = 20
    ema_period: int = 12
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bollinger_period: int = 20
    bollinger_std: int = 2


@dataclass
class StrategyConfig:
    confidence_threshold: float = 0.6
    rsi_oversold: int = 30
    rsi_overbought: int = 70
    stop_loss_pct: float = 2.0


@dataclass
class RiskConfig:
    max_position_value: int = 1000
    max_open_positions: int = 5
    daily_loss_limit: int = -500
    commission_per_trade: float = 1.0  # IBKR fixed rate ~$1 per trade


@dataclass
class Config:
    ibkr: IbkrConfig = field(default_factory=IbkrConfig)
    tickers: list[TickerConfig] = field(default_factory=list)
    market_data: MarketDataConfig = field(default_factory=MarketDataConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)

    @property
    def watchlist(self) -> list[str]:
        """Return list of ticker symbols for backward compatibility."""
        return [t.symbol for t in self.tickers]

    @watchlist.setter
    def watchlist(self, symbols: list[str]) -> None:
        """Set watchlist from plain symbols (keeps existing configs for known tickers)."""
        existing = {t.symbol: t for t in self.tickers}
        self.tickers = [existing.get(s, TickerConfig(symbol=s)) for s in symbols]

    def get_ticker(self, symbol: str) -> TickerConfig:
        """Get config for a specific ticker."""
        for t in self.tickers:
            if t.symbol == symbol:
                return t
        return TickerConfig(symbol=symbol)


def _parse_watchlist(raw_list: list) -> list[TickerConfig]:
    """Parse watchlist that can contain strings or dicts. Deduplicates by symbol."""
    tickers = []
    seen = set()
    for item in raw_list:
        if isinstance(item, str):
            if item not in seen:
                tickers.append(TickerConfig(symbol=item))
                seen.add(item)
        elif isinstance(item, dict):
            symbol = item["symbol"]
            if symbol not in seen:
                tickers.append(TickerConfig(
                    symbol=symbol,
                    exchange=item.get("exchange", "SMART"),
                    currency=item.get("currency", "USD"),
                ))
                seen.add(symbol)
    return tickers


def load_config(path: Path) -> Config:
    with open(path) as f:
        raw = yaml.safe_load(f)

    config = Config(
        ibkr=IbkrConfig(**raw.get("ibkr", {})),
        tickers=_parse_watchlist(raw.get("watchlist", ["SPY"])),
        market_data=MarketDataConfig(**raw.get("market_data", {})),
        analysis=AnalysisConfig(**raw.get("analysis", {})),
        strategy=StrategyConfig(**raw.get("strategy", {})),
        risk=RiskConfig(**raw.get("risk", {})),
    )
    config._path = path
    config._raw = raw
    return config


def save_config(config: Config) -> None:
    """Save the current config back to its YAML file."""
    path = getattr(config, "_path", None)
    raw = getattr(config, "_raw", None)
    if not path or not raw:
        return

    # Serialize tickers — use plain strings for US stocks, dicts for others
    watchlist = []
    for t in config.tickers:
        if t.exchange == "SMART" and t.currency == "USD":
            watchlist.append(t.symbol)
        else:
            watchlist.append({"symbol": t.symbol, "exchange": t.exchange, "currency": t.currency})
    raw["watchlist"] = watchlist

    with open(path, "w") as f:
        yaml.dump(raw, f, default_flow_style=False, sort_keys=False)
