from dataclasses import dataclass, field
from pathlib import Path

import yaml


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


@dataclass
class Config:
    ibkr: IbkrConfig = field(default_factory=IbkrConfig)
    watchlist: list[str] = field(default_factory=lambda: ["SPY"])
    market_data: MarketDataConfig = field(default_factory=MarketDataConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)


def load_config(path: Path) -> Config:
    with open(path) as f:
        raw = yaml.safe_load(f)

    return Config(
        ibkr=IbkrConfig(**raw.get("ibkr", {})),
        watchlist=raw.get("watchlist", ["SPY"]),
        market_data=MarketDataConfig(**raw.get("market_data", {})),
        analysis=AnalysisConfig(**raw.get("analysis", {})),
        strategy=StrategyConfig(**raw.get("strategy", {})),
        risk=RiskConfig(**raw.get("risk", {})),
    )
