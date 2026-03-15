# Stock Day Trader Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI app that streams IBKR market data, computes technical indicators, generates trading signals, and auto-executes paper trades.

**Architecture:** Modular service with 5 modules (market_data, analysis, strategy, execution, cli) orchestrated by an engine. Event-driven data flow via IBKR streaming callbacks. Rich terminal UI.

**Tech Stack:** Python 3.12+, ib_insync, pandas, pandas_ta, rich, pyyaml, pytest

---

## File Structure

| File | Responsibility |
|------|---------------|
| `pyproject.toml` | Project metadata, dependencies, entry point |
| `config.yaml` | Runtime configuration (IBKR, watchlist, strategy params, risk limits) |
| `src/stock_trader/__init__.py` | Package init, version |
| `src/stock_trader/models.py` | Shared data classes: Bar, IndicatorResult, Signal, Position, Trade |
| `src/stock_trader/config.py` | Load and validate config.yaml |
| `src/stock_trader/analysis.py` | Compute technical indicators from bar data |
| `src/stock_trader/strategy.py` | Evaluate indicators, produce signals |
| `src/stock_trader/execution.py` | Risk checks, order placement, position tracking |
| `src/stock_trader/market_data.py` | IBKR connection, streaming bars |
| `src/stock_trader/engine.py` | Orchestrator: wires modules, handles lifecycle |
| `src/stock_trader/cli.py` | Rich terminal UI and command handling |
| `src/stock_trader/main.py` | Entry point |
| `tests/test_models.py` | Tests for data models |
| `tests/test_config.py` | Tests for config loading |
| `tests/test_analysis.py` | Tests for indicator computation |
| `tests/test_strategy.py` | Tests for signal generation |
| `tests/test_execution.py` | Tests for risk limits and order logic |

**Note:** `models.py` is added vs. the spec to hold shared data classes, keeping each module free of circular imports.

---

## Chunk 1: Project Scaffolding & Data Models

### Task 1: Project Setup

**Files:**
- Create: `pyproject.toml`
- Create: `src/stock_trader/__init__.py`
- Create: `config.yaml`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "stock-trader"
version = "0.1.0"
description = "Day trading bot with IBKR integration"
requires-python = ">=3.12"
dependencies = [
    "ib_insync>=0.9.86",
    "pandas>=2.2.0",
    "pandas_ta>=0.3.14b1",
    "rich>=13.7.0",
    "pyyaml>=6.0.1",
]

[project.optional-dependencies]
dev = ["pytest>=8.0.0"]

[project.scripts]
stock-trader = "stock_trader.main:main"
```

- [ ] **Step 2: Create package init**

```python
# src/stock_trader/__init__.py
__version__ = "0.1.0"
```

- [ ] **Step 3: Create config.yaml**

```yaml
ibkr:
  host: "127.0.0.1"
  port: 7497
  client_id: 1

watchlist:
  - AAPL
  - TSLA
  - NVDA
  - SPY

market_data:
  bar_size: "5 secs"
  history_window: 100

analysis:
  sma_period: 20
  ema_period: 12
  rsi_period: 14
  macd_fast: 12
  macd_slow: 26
  macd_signal: 9
  bollinger_period: 20
  bollinger_std: 2

strategy:
  confidence_threshold: 0.6
  rsi_oversold: 30
  rsi_overbought: 70
  stop_loss_pct: 2.0

risk:
  max_position_value: 1000
  max_open_positions: 5
  daily_loss_limit: -500
```

- [ ] **Step 4: Install in dev mode**

Run: `cd /Users/yavorradulov/dev/stock-trader && python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
Expected: successful install, no errors

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml config.yaml src/stock_trader/__init__.py
git commit -m "feat: scaffold project with dependencies and config"
```

---

### Task 2: Data Models

**Files:**
- Create: `src/stock_trader/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing tests for data models**

```python
# tests/test_models.py
from datetime import datetime
from stock_trader.models import Bar, IndicatorResult, Signal, Position, Trade


def test_bar_creation():
    bar = Bar(
        timestamp=datetime(2026, 3, 15, 10, 30, 0),
        open=150.0,
        high=151.0,
        low=149.5,
        close=150.5,
        volume=1000,
    )
    assert bar.close == 150.5
    assert bar.volume == 1000


def test_indicator_result_creation():
    result = IndicatorResult(
        ticker="AAPL",
        sma=150.0,
        ema=150.5,
        rsi=45.0,
        macd=0.5,
        macd_signal=0.3,
        macd_hist=0.2,
        bb_upper=155.0,
        bb_middle=150.0,
        bb_lower=145.0,
        close=150.5,
    )
    assert result.ticker == "AAPL"
    assert result.rsi == 45.0


def test_signal_creation():
    signal = Signal(
        ticker="AAPL",
        action="BUY",
        confidence=0.8,
        reason="RSI oversold + price above SMA20",
    )
    assert signal.action == "BUY"
    assert signal.confidence == 0.8


def test_signal_is_actionable():
    buy = Signal(ticker="AAPL", action="BUY", confidence=0.8, reason="test")
    hold = Signal(ticker="AAPL", action="HOLD", confidence=0.5, reason="test")
    low_conf = Signal(ticker="AAPL", action="BUY", confidence=0.3, reason="test")
    assert buy.is_actionable(threshold=0.6) is True
    assert hold.is_actionable(threshold=0.6) is False
    assert low_conf.is_actionable(threshold=0.6) is False


def test_position_creation_and_pnl():
    pos = Position(
        ticker="AAPL",
        quantity=10,
        entry_price=150.0,
    )
    assert pos.unrealized_pnl(current_price=155.0) == 50.0
    assert pos.unrealized_pnl(current_price=145.0) == -50.0


def test_trade_creation():
    trade = Trade(
        timestamp=datetime(2026, 3, 15, 10, 30, 0),
        ticker="AAPL",
        action="BUY",
        quantity=10,
        price=150.0,
        reason="RSI oversold",
    )
    assert trade.ticker == "AAPL"
    assert trade.action == "BUY"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/yavorradulov/dev/stock-trader && source .venv/bin/activate && pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'stock_trader.models'`

- [ ] **Step 3: Implement models**

```python
# src/stock_trader/models.py
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass
class IndicatorResult:
    ticker: str
    sma: float | None = None
    ema: float | None = None
    rsi: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    close: float | None = None


@dataclass
class Signal:
    ticker: str
    action: str  # "BUY", "SELL", "HOLD"
    confidence: float
    reason: str

    def is_actionable(self, threshold: float) -> bool:
        return self.action in ("BUY", "SELL") and self.confidence >= threshold


@dataclass
class Position:
    ticker: str
    quantity: int
    entry_price: float

    def unrealized_pnl(self, current_price: float) -> float:
        return (current_price - self.entry_price) * self.quantity


@dataclass
class Trade:
    timestamp: datetime
    ticker: str
    action: str  # "BUY", "SELL"
    quantity: int
    price: float
    reason: str
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/yavorradulov/dev/stock-trader && source .venv/bin/activate && pytest tests/test_models.py -v`
Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_trader/models.py tests/test_models.py
git commit -m "feat: add data models (Bar, Signal, Position, Trade)"
```

---

### Task 3: Config Loading

**Files:**
- Create: `src/stock_trader/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing tests for config**

```python
# tests/test_config.py
import tempfile
from pathlib import Path
from stock_trader.config import load_config, Config


def test_load_config_from_file():
    yaml_content = """
ibkr:
  host: "127.0.0.1"
  port: 7497
  client_id: 1
watchlist:
  - AAPL
  - TSLA
market_data:
  bar_size: "5 secs"
  history_window: 100
analysis:
  sma_period: 20
  ema_period: 12
  rsi_period: 14
  macd_fast: 12
  macd_slow: 26
  macd_signal: 9
  bollinger_period: 20
  bollinger_std: 2
strategy:
  confidence_threshold: 0.6
  rsi_oversold: 30
  rsi_overbought: 70
  stop_loss_pct: 2.0
risk:
  max_position_value: 1000
  max_open_positions: 5
  daily_loss_limit: -500
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        config = load_config(Path(f.name))

    assert config.ibkr.host == "127.0.0.1"
    assert config.ibkr.port == 7497
    assert config.watchlist == ["AAPL", "TSLA"]
    assert config.analysis.rsi_period == 14
    assert config.strategy.confidence_threshold == 0.6
    assert config.risk.max_position_value == 1000
    assert config.risk.daily_loss_limit == -500


def test_config_defaults():
    yaml_content = """
ibkr:
  host: "127.0.0.1"
  port: 7497
  client_id: 1
watchlist:
  - SPY
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        config = load_config(Path(f.name))

    # Should use defaults for missing sections
    assert config.analysis.sma_period == 20
    assert config.strategy.rsi_oversold == 30
    assert config.risk.max_open_positions == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'stock_trader.config'`

- [ ] **Step 3: Implement config**

```python
# src/stock_trader/config.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: all 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_trader/config.py tests/test_config.py
git commit -m "feat: add config loading with defaults"
```

---

## Chunk 2: Analysis & Strategy Modules

### Task 4: Analysis Module

**Files:**
- Create: `src/stock_trader/analysis.py`
- Create: `tests/test_analysis.py`

- [ ] **Step 1: Write failing tests for analysis**

```python
# tests/test_analysis.py
from datetime import datetime, timedelta
from stock_trader.models import Bar, IndicatorResult
from stock_trader.config import AnalysisConfig
from stock_trader.analysis import compute_indicators


def _make_bars(prices: list[float]) -> list[Bar]:
    """Helper: create bars from a list of close prices."""
    base = datetime(2026, 3, 15, 9, 30, 0)
    bars = []
    for i, price in enumerate(prices):
        bars.append(Bar(
            timestamp=base + timedelta(seconds=5 * i),
            open=price - 0.1,
            high=price + 0.5,
            low=price - 0.5,
            close=price,
            volume=1000,
        ))
    return bars


def test_compute_indicators_returns_result():
    # Need enough bars for longest indicator (SMA 20)
    prices = [150.0 + i * 0.1 for i in range(30)]
    bars = _make_bars(prices)
    config = AnalysisConfig()
    result = compute_indicators("AAPL", bars, config)
    assert isinstance(result, IndicatorResult)
    assert result.ticker == "AAPL"


def test_compute_indicators_sma():
    prices = [150.0 + i * 0.1 for i in range(30)]
    bars = _make_bars(prices)
    config = AnalysisConfig(sma_period=20)
    result = compute_indicators("AAPL", bars, config)
    assert result.sma is not None
    # SMA of last 20 prices should be close to the middle of those prices
    last_20 = prices[-20:]
    expected_sma = sum(last_20) / 20
    assert abs(result.sma - expected_sma) < 0.01


def test_compute_indicators_rsi():
    # Uptrend: RSI should be > 50
    prices = [100.0 + i * 1.0 for i in range(30)]
    bars = _make_bars(prices)
    config = AnalysisConfig()
    result = compute_indicators("AAPL", bars, config)
    assert result.rsi is not None
    assert result.rsi > 50


def test_compute_indicators_insufficient_data():
    # Only 5 bars — not enough for SMA 20
    prices = [150.0 + i for i in range(5)]
    bars = _make_bars(prices)
    config = AnalysisConfig()
    result = compute_indicators("AAPL", bars, config)
    assert result.sma is None  # Not enough data


def test_compute_indicators_bollinger():
    prices = [150.0 + i * 0.1 for i in range(30)]
    bars = _make_bars(prices)
    config = AnalysisConfig()
    result = compute_indicators("AAPL", bars, config)
    assert result.bb_upper is not None
    assert result.bb_lower is not None
    assert result.bb_upper > result.bb_lower


def test_compute_indicators_macd():
    prices = [150.0 + i * 0.1 for i in range(40)]
    bars = _make_bars(prices)
    config = AnalysisConfig()
    result = compute_indicators("AAPL", bars, config)
    assert result.macd is not None
    assert result.macd_signal is not None
    assert result.macd_hist is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_analysis.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'stock_trader.analysis'`

- [ ] **Step 3: Implement analysis**

```python
# src/stock_trader/analysis.py
import pandas as pd
import pandas_ta as ta

from stock_trader.config import AnalysisConfig
from stock_trader.models import Bar, IndicatorResult


def compute_indicators(
    ticker: str,
    bars: list[Bar],
    config: AnalysisConfig,
) -> IndicatorResult:
    if len(bars) < 2:
        return IndicatorResult(ticker=ticker)

    df = pd.DataFrame([
        {"close": b.close, "high": b.high, "low": b.low, "open": b.open, "volume": b.volume}
        for b in bars
    ])

    result = IndicatorResult(ticker=ticker, close=bars[-1].close)

    # SMA
    sma = ta.sma(df["close"], length=config.sma_period)
    if sma is not None and not sma.empty:
        val = sma.iloc[-1]
        result.sma = None if pd.isna(val) else float(val)

    # EMA
    ema = ta.ema(df["close"], length=config.ema_period)
    if ema is not None and not ema.empty:
        val = ema.iloc[-1]
        result.ema = None if pd.isna(val) else float(val)

    # RSI
    rsi = ta.rsi(df["close"], length=config.rsi_period)
    if rsi is not None and not rsi.empty:
        val = rsi.iloc[-1]
        result.rsi = None if pd.isna(val) else float(val)

    # MACD
    macd_df = ta.macd(
        df["close"],
        fast=config.macd_fast,
        slow=config.macd_slow,
        signal=config.macd_signal,
    )
    if macd_df is not None and not macd_df.empty:
        row = macd_df.iloc[-1]
        result.macd = None if pd.isna(row.iloc[0]) else float(row.iloc[0])
        result.macd_hist = None if pd.isna(row.iloc[1]) else float(row.iloc[1])
        result.macd_signal = None if pd.isna(row.iloc[2]) else float(row.iloc[2])

    # Bollinger Bands
    bbands = ta.bbands(
        df["close"],
        length=config.bollinger_period,
        std=config.bollinger_std,
    )
    if bbands is not None and not bbands.empty:
        row = bbands.iloc[-1]
        result.bb_lower = None if pd.isna(row.iloc[0]) else float(row.iloc[0])
        result.bb_middle = None if pd.isna(row.iloc[1]) else float(row.iloc[1])
        result.bb_upper = None if pd.isna(row.iloc[2]) else float(row.iloc[2])

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_analysis.py -v`
Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_trader/analysis.py tests/test_analysis.py
git commit -m "feat: add analysis module with technical indicators"
```

---

### Task 5: Strategy Module

**Files:**
- Create: `src/stock_trader/strategy.py`
- Create: `tests/test_strategy.py`

- [ ] **Step 1: Write failing tests for strategy**

```python
# tests/test_strategy.py
from stock_trader.models import IndicatorResult, Signal
from stock_trader.config import StrategyConfig
from stock_trader.strategy import evaluate


def test_buy_signal_rsi_oversold_above_sma():
    indicators = IndicatorResult(
        ticker="AAPL",
        rsi=25.0,       # oversold
        sma=148.0,
        close=150.0,    # above SMA
        ema=149.0,
        macd=0.5,
        macd_signal=0.3,
        macd_hist=0.2,
        bb_upper=155.0,
        bb_middle=150.0,
        bb_lower=145.0,
    )
    config = StrategyConfig()
    signal = evaluate(indicators, config)
    assert signal.action == "BUY"
    assert signal.confidence >= config.confidence_threshold


def test_sell_signal_rsi_overbought():
    indicators = IndicatorResult(
        ticker="AAPL",
        rsi=75.0,       # overbought
        sma=150.0,
        close=149.0,    # below SMA
        ema=149.5,
        macd=-0.5,
        macd_signal=-0.3,
        macd_hist=-0.2,
        bb_upper=155.0,
        bb_middle=150.0,
        bb_lower=145.0,
    )
    config = StrategyConfig()
    signal = evaluate(indicators, config)
    assert signal.action == "SELL"


def test_hold_signal_neutral():
    indicators = IndicatorResult(
        ticker="AAPL",
        rsi=50.0,       # neutral
        sma=150.0,
        close=150.5,    # near SMA
        ema=150.2,
        macd=0.01,
        macd_signal=0.01,
        macd_hist=0.0,
        bb_upper=155.0,
        bb_middle=150.0,
        bb_lower=145.0,
    )
    config = StrategyConfig()
    signal = evaluate(indicators, config)
    assert signal.action == "HOLD"


def test_hold_when_insufficient_data():
    indicators = IndicatorResult(
        ticker="AAPL",
        rsi=None,
        sma=None,
        close=150.0,
    )
    config = StrategyConfig()
    signal = evaluate(indicators, config)
    assert signal.action == "HOLD"
    assert signal.confidence == 0.0


def test_sell_price_below_sma():
    indicators = IndicatorResult(
        ticker="AAPL",
        rsi=55.0,       # neutral RSI
        sma=152.0,
        close=149.0,    # well below SMA
        ema=150.0,
        macd=-0.5,
        macd_signal=-0.3,
        macd_hist=-0.2,
        bb_upper=155.0,
        bb_middle=150.0,
        bb_lower=145.0,
    )
    config = StrategyConfig()
    signal = evaluate(indicators, config)
    assert signal.action == "SELL"


def test_confidence_increases_with_confirming_indicators():
    # Buy with multiple confirmations: RSI oversold + above SMA + MACD bullish + near lower BB
    strong_buy = IndicatorResult(
        ticker="AAPL",
        rsi=22.0,
        sma=148.0,
        close=149.0,     # above SMA and near lower BB
        ema=147.0,
        macd=0.5,
        macd_signal=0.3,
        macd_hist=0.2,   # positive histogram = bullish
        bb_upper=155.0,
        bb_middle=150.0,
        bb_lower=145.5,  # close near lower band
    )
    # Buy with fewer confirmations: just RSI oversold + above SMA
    weak_buy = IndicatorResult(
        ticker="AAPL",
        rsi=28.0,
        sma=148.0,
        close=150.0,
        ema=149.0,
        macd=-0.1,
        macd_signal=0.1,
        macd_hist=-0.2,  # negative histogram = not confirming
        bb_upper=155.0,
        bb_middle=150.0,
        bb_lower=145.0,
    )
    config = StrategyConfig()
    strong = evaluate(strong_buy, config)
    weak = evaluate(weak_buy, config)
    assert strong.action == "BUY"
    assert weak.action == "BUY"
    assert strong.confidence >= weak.confidence
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_strategy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'stock_trader.strategy'`

- [ ] **Step 3: Implement strategy**

```python
# src/stock_trader/strategy.py
from stock_trader.config import StrategyConfig
from stock_trader.models import IndicatorResult, Signal


def evaluate(indicators: IndicatorResult, config: StrategyConfig) -> Signal:
    """Evaluate indicators and produce a trading signal."""
    if indicators.rsi is None or indicators.sma is None or indicators.close is None:
        return Signal(
            ticker=indicators.ticker,
            action="HOLD",
            confidence=0.0,
            reason="Insufficient indicator data",
        )

    buy_reasons: list[str] = []
    sell_reasons: list[str] = []

    # RSI
    if indicators.rsi < config.rsi_oversold:
        buy_reasons.append(f"RSI oversold ({indicators.rsi:.0f})")
    elif indicators.rsi > config.rsi_overbought:
        sell_reasons.append(f"RSI overbought ({indicators.rsi:.0f})")

    # Price vs SMA
    if indicators.close > indicators.sma:
        buy_reasons.append("price above SMA")
    else:
        sell_reasons.append("price below SMA")

    # MACD histogram
    if indicators.macd_hist is not None:
        if indicators.macd_hist > 0:
            buy_reasons.append("MACD bullish")
        else:
            sell_reasons.append("MACD bearish")

    # Bollinger Bands
    if indicators.bb_lower is not None and indicators.bb_upper is not None:
        bb_range = indicators.bb_upper - indicators.bb_lower
        if bb_range > 0:
            closeness_to_lower = (indicators.close - indicators.bb_lower) / bb_range
            if closeness_to_lower < 0.2:
                buy_reasons.append("near lower Bollinger Band")
            elif closeness_to_lower > 0.8:
                sell_reasons.append("near upper Bollinger Band")

    # Decision logic
    total_signals = len(buy_reasons) + len(sell_reasons)
    if total_signals == 0:
        return Signal(
            ticker=indicators.ticker,
            action="HOLD",
            confidence=0.0,
            reason="No clear signals",
        )

    # Buy requires: RSI oversold AND price above SMA (minimum)
    rsi_oversold = indicators.rsi < config.rsi_oversold
    price_above_sma = indicators.close > indicators.sma

    if rsi_oversold and price_above_sma:
        confidence = len(buy_reasons) / 4.0  # 4 possible buy indicators
        return Signal(
            ticker=indicators.ticker,
            action="BUY",
            confidence=min(confidence, 1.0),
            reason=" + ".join(buy_reasons),
        )

    # Sell if: RSI overbought OR price below SMA
    rsi_overbought = indicators.rsi > config.rsi_overbought
    price_below_sma = indicators.close < indicators.sma

    if rsi_overbought or price_below_sma:
        confidence = len(sell_reasons) / 4.0
        return Signal(
            ticker=indicators.ticker,
            action="SELL",
            confidence=min(confidence, 1.0),
            reason=" + ".join(sell_reasons),
        )

    return Signal(
        ticker=indicators.ticker,
        action="HOLD",
        confidence=0.0,
        reason="Mixed signals",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_strategy.py -v`
Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_trader/strategy.py tests/test_strategy.py
git commit -m "feat: add strategy module with signal generation rules"
```

---

## Chunk 3: Execution Module

### Task 6: Execution Module

**Files:**
- Create: `src/stock_trader/execution.py`
- Create: `tests/test_execution.py`

- [ ] **Step 1: Write failing tests for execution**

```python
# tests/test_execution.py
from datetime import datetime
from stock_trader.models import Signal, Position, Trade
from stock_trader.config import RiskConfig
from stock_trader.execution import ExecutionManager


def test_execute_buy_creates_position():
    mgr = ExecutionManager(config=RiskConfig(), place_order_fn=None)
    signal = Signal(ticker="AAPL", action="BUY", confidence=0.8, reason="test")
    result = mgr.process_signal(signal, current_price=150.0)
    assert result is not None
    assert result.action == "BUY"
    assert "AAPL" in mgr.positions


def test_execute_buy_respects_max_position_value():
    config = RiskConfig(max_position_value=1000)
    mgr = ExecutionManager(config=config, place_order_fn=None)
    signal = Signal(ticker="AAPL", action="BUY", confidence=0.8, reason="test")
    result = mgr.process_signal(signal, current_price=150.0)
    # quantity = floor(1000 / 150) = 6
    assert mgr.positions["AAPL"].quantity == 6


def test_execute_buy_blocked_by_existing_position():
    mgr = ExecutionManager(config=RiskConfig(), place_order_fn=None)
    signal = Signal(ticker="AAPL", action="BUY", confidence=0.8, reason="test")
    mgr.process_signal(signal, current_price=150.0)
    # Second buy on same ticker should be blocked
    result = mgr.process_signal(signal, current_price=151.0)
    assert result is None


def test_execute_buy_blocked_by_max_positions():
    config = RiskConfig(max_open_positions=2)
    mgr = ExecutionManager(config=config, place_order_fn=None)
    for ticker in ["AAPL", "TSLA"]:
        signal = Signal(ticker=ticker, action="BUY", confidence=0.8, reason="test")
        mgr.process_signal(signal, current_price=100.0)
    # Third position should be blocked
    signal = Signal(ticker="NVDA", action="BUY", confidence=0.8, reason="test")
    result = mgr.process_signal(signal, current_price=100.0)
    assert result is None


def test_execute_sell_closes_position():
    mgr = ExecutionManager(config=RiskConfig(), place_order_fn=None)
    buy = Signal(ticker="AAPL", action="BUY", confidence=0.8, reason="test")
    mgr.process_signal(buy, current_price=150.0)
    sell = Signal(ticker="AAPL", action="SELL", confidence=0.8, reason="test")
    result = mgr.process_signal(sell, current_price=155.0)
    assert result is not None
    assert result.action == "SELL"
    assert "AAPL" not in mgr.positions


def test_execute_sell_ignored_without_position():
    mgr = ExecutionManager(config=RiskConfig(), place_order_fn=None)
    signal = Signal(ticker="AAPL", action="SELL", confidence=0.8, reason="test")
    result = mgr.process_signal(signal, current_price=150.0)
    assert result is None


def test_daily_loss_limit_halts_trading():
    config = RiskConfig(daily_loss_limit=-100, max_position_value=10000)
    mgr = ExecutionManager(config=config, place_order_fn=None)
    # Buy and sell at a loss
    buy = Signal(ticker="AAPL", action="BUY", confidence=0.8, reason="test")
    mgr.process_signal(buy, current_price=100.0)
    sell = Signal(ticker="AAPL", action="SELL", confidence=0.8, reason="test")
    mgr.process_signal(sell, current_price=98.0)  # lose $2 * qty
    # Check if trading halted (daily_pnl should exceed limit after enough loss)
    # With max_position_value=10000, qty=100, loss = 100*2 = $200
    assert mgr.is_halted is True


def test_trade_history_tracking():
    mgr = ExecutionManager(config=RiskConfig(), place_order_fn=None)
    signal = Signal(ticker="AAPL", action="BUY", confidence=0.8, reason="test")
    mgr.process_signal(signal, current_price=150.0)
    assert len(mgr.trades) == 1
    assert mgr.trades[0].ticker == "AAPL"
    assert mgr.trades[0].action == "BUY"


def test_daily_pnl_tracking():
    mgr = ExecutionManager(config=RiskConfig(max_position_value=1500), place_order_fn=None)
    buy = Signal(ticker="AAPL", action="BUY", confidence=0.8, reason="test")
    mgr.process_signal(buy, current_price=150.0)  # qty = 10
    sell = Signal(ticker="AAPL", action="SELL", confidence=0.8, reason="test")
    mgr.process_signal(sell, current_price=155.0)  # profit = 10 * 5 = $50
    assert mgr.daily_pnl == 50.0


def test_check_stop_losses_triggers_sell():
    mgr = ExecutionManager(config=RiskConfig(max_position_value=1000), place_order_fn=None)
    buy = Signal(ticker="AAPL", action="BUY", confidence=0.8, reason="test")
    mgr.process_signal(buy, current_price=100.0)  # qty = 10, entry = 100
    # Price dropped 3% — should trigger stop-loss at 2%
    signals = mgr.check_stop_losses(prices={"AAPL": 97.0}, stop_loss_pct=2.0)
    assert len(signals) == 1
    assert signals[0].ticker == "AAPL"
    assert signals[0].action == "SELL"
    assert "Stop-loss" in signals[0].reason


def test_check_stop_losses_no_trigger():
    mgr = ExecutionManager(config=RiskConfig(max_position_value=1000), place_order_fn=None)
    buy = Signal(ticker="AAPL", action="BUY", confidence=0.8, reason="test")
    mgr.process_signal(buy, current_price=100.0)
    # Price dropped only 1% — should NOT trigger stop-loss at 2%
    signals = mgr.check_stop_losses(prices={"AAPL": 99.0}, stop_loss_pct=2.0)
    assert len(signals) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_execution.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'stock_trader.execution'`

- [ ] **Step 3: Implement execution**

```python
# src/stock_trader/execution.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_execution.py -v`
Expected: all 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_trader/execution.py tests/test_execution.py
git commit -m "feat: add execution module with risk management"
```

---

## Chunk 4: Market Data & Engine

### Task 7: Market Data Module

**Files:**
- Create: `src/stock_trader/market_data.py`

No unit tests for this module — it wraps `ib_insync` which requires a live IBKR connection. Integration-tested via the engine.

**Note:** The spec mentions a "fallback polling mode" for testing with historical data. This is deferred to a future task — the initial implementation focuses on the streaming path only.

- [ ] **Step 1: Implement market_data**

```python
# src/stock_trader/market_data.py
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
```

- [ ] **Step 2: Commit**

```bash
git add src/stock_trader/market_data.py
git commit -m "feat: add market data module with IBKR streaming"
```

---

### Task 8: Engine Module

**Files:**
- Create: `src/stock_trader/engine.py`

- [ ] **Step 1: Implement engine**

```python
# src/stock_trader/engine.py
import logging
from typing import Callable

from stock_trader.config import Config
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

        for ticker in self.config.watchlist:
            logger.info("Subscribing to %s", ticker)
            self.market_data.subscribe(ticker)

        logger.info("Engine started. Streaming market data.")

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
            logger.info("Added %s to watchlist", ticker)

    def remove_ticker(self, ticker: str) -> None:
        if ticker in self.config.watchlist:
            self.config.watchlist.remove(ticker)
            self.market_data.unsubscribe(ticker)
            logger.info("Removed %s from watchlist", ticker)

    def pause(self) -> None:
        self.execution.is_paused = True
        logger.info("Trading paused")

    def resume(self) -> None:
        self.execution.is_paused = False
        logger.info("Trading resumed")
```

- [ ] **Step 2: Commit**

```bash
git add src/stock_trader/engine.py
git commit -m "feat: add engine orchestrator"
```

---

## Chunk 5: CLI & Entry Point

### Task 9: CLI Module

**Files:**
- Create: `src/stock_trader/cli.py`

- [ ] **Step 1: Implement CLI**

```python
# src/stock_trader/cli.py
import threading
from datetime import datetime

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from stock_trader.engine import Engine
from stock_trader.models import Signal, Trade


class TradingCLI:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.console = Console()
        self.signals: dict[str, Signal] = {}  # latest signal per ticker
        self._running = False

        # Register callbacks
        self.engine.on_signal = self._on_signal
        self.engine.on_trade = self._on_trade

    def _on_signal(self, signal: Signal) -> None:
        self.signals[signal.ticker] = signal

    def _on_trade(self, trade: Trade) -> None:
        pass  # Trades are tracked in engine.execution.trades

    def _build_watchlist_table(self) -> Table:
        table = Table(title="Watchlist", expand=True)
        table.add_column("Ticker", style="bold")
        table.add_column("Price", justify="right")
        table.add_column("Change", justify="right")
        table.add_column("RSI", justify="right")
        table.add_column("MACD", justify="center")
        table.add_column("Signal", justify="center")

        for ticker in self.engine.config.watchlist:
            bars = self.engine.market_data.get_bars(ticker)
            price = f"{bars[-1].close:.2f}" if bars else "---"

            # Calculate price change from previous bar
            change_str = "---"
            if bars and len(bars) >= 2:
                prev = bars[-2].close
                curr = bars[-1].close
                pct = (curr - prev) / prev * 100
                color = "green" if pct >= 0 else "red"
                change_str = f"[{color}]{pct:+.1f}%[/{color}]"

            signal = self.signals.get(ticker)
            rsi_str = "---"
            macd_str = "---"
            signal_str = "---"

            if signal:
                # Get RSI from latest analysis
                from stock_trader.analysis import compute_indicators
                indicators = compute_indicators(
                    ticker, bars, self.engine.config.analysis
                ) if bars else None

                if indicators and indicators.rsi is not None:
                    rsi_val = indicators.rsi
                    rsi_str = f"{rsi_val:.0f}"
                    if rsi_val < 30:
                        rsi_str = f"[red]{rsi_str}[/red]"
                    elif rsi_val > 70:
                        rsi_str = f"[green]{rsi_str}[/green]"

                if indicators and indicators.macd_hist is not None:
                    macd_str = "[green]▲[/green]" if indicators.macd_hist > 0 else "[red]▼[/red]"

                if signal.action == "BUY":
                    signal_str = f"[bold green]BUY ({signal.confidence:.0%})[/bold green]"
                elif signal.action == "SELL":
                    signal_str = f"[bold red]SELL ({signal.confidence:.0%})[/bold red]"
                else:
                    signal_str = "[dim]HOLD[/dim]"

            table.add_row(ticker, price, change_str, rsi_str, macd_str, signal_str)

        return table

    def _build_positions_table(self) -> Table:
        table = Table(title="Positions", expand=True)
        table.add_column("Ticker", style="bold")
        table.add_column("Qty", justify="right")
        table.add_column("Entry", justify="right")
        table.add_column("Current", justify="right")
        table.add_column("P/L", justify="right")

        for ticker, pos in self.engine.execution.positions.items():
            bars = self.engine.market_data.get_bars(ticker)
            current = bars[-1].close if bars else pos.entry_price
            pnl = pos.unrealized_pnl(current)
            pnl_style = "green" if pnl >= 0 else "red"

            table.add_row(
                ticker,
                str(pos.quantity),
                f"{pos.entry_price:.2f}",
                f"{current:.2f}",
                f"[{pnl_style}]{pnl:+.2f}[/{pnl_style}]",
            )

        if not self.engine.execution.positions:
            table.add_row("[dim]No open positions[/dim]", "", "", "", "")

        return table

    def _build_trades_table(self) -> Table:
        table = Table(title="Trade Log", expand=True)
        table.add_column("Time")
        table.add_column("Action", justify="center")
        table.add_column("Ticker")
        table.add_column("Qty", justify="right")
        table.add_column("Price", justify="right")
        table.add_column("Reason")

        # Show last 10 trades
        for trade in self.engine.execution.trades[-10:]:
            action_style = "green" if trade.action == "BUY" else "red"
            table.add_row(
                trade.timestamp.strftime("%H:%M:%S"),
                f"[{action_style}]{trade.action}[/{action_style}]",
                trade.ticker,
                str(trade.quantity),
                f"{trade.price:.2f}",
                trade.reason[:40],
            )

        if not self.engine.execution.trades:
            table.add_row("[dim]No trades yet[/dim]", "", "", "", "", "")

        return table

    def _build_status_bar(self) -> Text:
        exec_mgr = self.engine.execution
        pnl = exec_mgr.daily_pnl
        pnl_color = "green" if pnl >= 0 else "red"
        trade_count = len(exec_mgr.trades)
        limit = self.engine.config.risk.daily_loss_limit
        limit_used = abs(min(pnl, 0) / abs(limit) * 100) if limit != 0 else 0

        status = "HALTED" if exec_mgr.is_halted else "PAUSED" if exec_mgr.is_paused else "ACTIVE"
        status_color = "red" if exec_mgr.is_halted else "yellow" if exec_mgr.is_paused else "green"
        connected = self.engine.market_data.ib.isConnected()
        conn_str = "[green]Connected[/green]" if connected else "[red]Disconnected[/red]"

        text = Text()
        text.append(f"  Daily P/L: ", style="bold")
        text.append(f"${pnl:+.2f}", style=pnl_color)
        text.append(f"  |  Trades: {trade_count}")
        text.append(f"  |  Loss limit: {limit_used:.0f}%")
        text.append(f"  |  Status: ")
        text.append(status, style=status_color)
        text.append(f"  |  IBKR: ")
        text.append_text(Text.from_markup(conn_str))
        return text

    def _build_display(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(Panel(self._build_watchlist_table()), name="watchlist", ratio=3),
            Layout(Panel(self._build_positions_table()), name="positions", ratio=2),
            Layout(Panel(self._build_trades_table()), name="trades", ratio=3),
            Layout(Panel(self._build_status_bar()), name="status", size=3),
        )
        return layout

    def _input_loop(self) -> None:
        """Handle user commands in a background thread."""
        while self._running:
            try:
                cmd = input().strip().lower()
            except EOFError:
                break

            parts = cmd.split()
            if not parts:
                continue

            command = parts[0]

            if command == "quit":
                self._running = False
                self.engine.stop()
                break
            elif command == "add" and len(parts) == 2:
                self.engine.add_ticker(parts[1].upper())
            elif command == "remove" and len(parts) == 2:
                self.engine.remove_ticker(parts[1].upper())
            elif command == "pause":
                self.engine.pause()
            elif command == "resume":
                self.engine.resume()
            elif command == "status":
                self.console.print(f"Connected: {self.engine.market_data.ib.isConnected()}")
            elif command == "trades":
                for t in self.engine.execution.trades:
                    self.console.print(
                        f"{t.timestamp:%H:%M:%S} {t.action} {t.ticker} "
                        f"{t.quantity}x @ {t.price:.2f} ({t.reason})"
                    )

    def run(self) -> None:
        self._running = True

        # Start command input in background thread
        input_thread = threading.Thread(target=self._input_loop, daemon=True)
        input_thread.start()

        with Live(self._build_display(), refresh_per_second=2, console=self.console) as live:
            while self._running:
                self.engine.sleep(0.5)
                live.update(self._build_display())
```

- [ ] **Step 2: Commit**

```bash
git add src/stock_trader/cli.py
git commit -m "feat: add Rich terminal UI with live display"
```

---

### Task 10: Entry Point

**Files:**
- Create: `src/stock_trader/main.py`

- [ ] **Step 1: Implement main**

```python
# src/stock_trader/main.py
import argparse
import logging
import sys
from pathlib import Path

from stock_trader.config import load_config
from stock_trader.engine import Engine
from stock_trader.cli import TradingCLI


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock Day Trader")
    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to config file (default: config.yaml)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if not args.config.exists():
        print(f"Config file not found: {args.config}")
        sys.exit(1)

    config = load_config(args.config)

    print(f"Stock Day Trader v0.1.0")
    print(f"Connecting to IBKR at {config.ibkr.host}:{config.ibkr.port} (paper trading)")
    print(f"Watchlist: {', '.join(config.watchlist)}")
    print()

    engine = Engine(config)
    cli = TradingCLI(engine)

    try:
        engine.start()
        cli.run()
    except KeyboardInterrupt:
        print("\nShutting down...")
    except ConnectionRefusedError:
        print(f"\nCould not connect to IBKR at {config.ibkr.host}:{config.ibkr.port}")
        print("Make sure TWS or IB Gateway is running with API connections enabled.")
        sys.exit(1)
    finally:
        engine.stop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add src/stock_trader/main.py
git commit -m "feat: add entry point with CLI argument parsing"
```

---

### Task 11: Run All Tests & Final Commit

- [ ] **Step 1: Run full test suite**

Run: `cd /Users/yavorradulov/dev/stock-trader && source .venv/bin/activate && pytest tests/ -v`
Expected: all tests PASS (models: 6, config: 2, analysis: 6, strategy: 6, execution: 11 = 31 tests)

- [ ] **Step 2: Verify the app starts (will fail to connect to IBKR but should not crash on import)**

Run: `cd /Users/yavorradulov/dev/stock-trader && source .venv/bin/activate && python -c "from stock_trader.main import main; print('Import OK')"`
Expected: `Import OK`

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "chore: verify full test suite passes"
```
