# Stock Day Trader — Design Spec

## Overview

A Python CLI application that connects to Interactive Brokers via `ib_insync`, streams real-time market data for a configurable watchlist of US stocks, computes technical indicators, generates buy/sell signals, and automatically executes paper trades. The terminal UI displays live watchlist data, positions, trade log, and daily P/L.

## Architecture

Modular service architecture with streaming data input. Five modules with clear boundaries, orchestrated by a central engine.

```
┌─────────────────────────────────────────────┐
│                    CLI                       │
│  (Rich terminal UI: watchlist, signals, log) │
├─────────────────────────────────────────────┤
│                  Engine                      │
│  (Orchestrator: lifecycle, module wiring)    │
├──────┬──────────┬───────────┬───────────────┤
│Market│ Analysis │ Strategy  │  Execution    │
│ Data │          │           │               │
│IBKR  │ RSI,SMA, │ Buy/sell  │ ib_insync     │
│stream│ MACD,    │ rules     │ paper trading │
│      │ Bollinger│ engine    │ orders        │
└──────┴──────────┴───────────┴───────────────┘
```

### Modules

1. **Market Data** (`market_data.py`) — Connects to IBKR via `ib_insync`. Subscribes to real-time 5-second bars for each ticker in the watchlist. Maintains a rolling window of bar history per ticker (configurable, default 100 bars). Provides the data to Analysis on each new bar callback.

2. **Analysis** (`analysis.py`) — Receives bar data, computes technical indicators using `pandas_ta`:
   - SMA (20-period)
   - EMA (12-period)
   - RSI (14-period)
   - MACD (12, 26, 9)
   - Bollinger Bands (20-period, 2 std dev)
   All parameters configurable via config file.

3. **Strategy** (`strategy.py`) — Evaluates indicator values against rules and produces signals:
   ```
   Signal = {
     ticker: str,
     action: "BUY" | "SELL" | "HOLD",
     confidence: float (0.0-1.0),
     reason: str
   }
   ```
   Initial rules:
   - **BUY**: RSI < 30 (oversold) AND price crosses above SMA20
   - **SELL**: RSI > 70 (overbought) OR price crosses below SMA20 OR stop-loss hit
   - Confidence derived from number of agreeing indicators
   - Only BUY/SELL signals above a configurable confidence threshold are forwarded to Execution.

4. **Execution** (`execution.py`) — Receives actionable signals, enforces risk limits, places paper orders via IBKR, tracks open positions and trade history.

   Risk limits (all configurable):
   - Max position size per ticker (default: $1,000)
   - Max open positions (default: 5)
   - Daily loss limit — halts trading when hit (default: -$500)
   - No double-entry — won't buy a ticker already held

5. **CLI** (`cli.py`) — Rich terminal UI with live-updating panels:
   - Watchlist: ticker, price, change, RSI, MACD trend, signal
   - Positions: ticker, qty, entry price, current price, P/L
   - Trade log: timestamp, action, ticker, qty, price, reason
   - Status bar: daily P/L, trade count, loss limit usage, IBKR connection status

   Interactive commands:
   - `add TICKER` / `remove TICKER` — modify watchlist at runtime
   - `status` — connection & account info
   - `trades` — full trade history
   - `pause` / `resume` — pause/resume automated trading
   - `quit` — graceful shutdown

## Data Flow

Event-driven via IBKR streaming:

```
Startup:
  1. Engine loads config
  2. Market Data connects to IBKR, subscribes to bars for watchlist
  3. CLI starts rendering

On each new bar (streaming callback):
  1. Market Data receives bar, updates rolling window
  2. Analysis computes indicators on updated data
  3. Strategy evaluates rules, emits signal
  4. If signal is BUY/SELL with sufficient confidence:
     - Execution checks risk limits
     - Places paper order if limits allow
     - Updates positions and trade log
  5. CLI refreshes display
```

Fallback: polling mode for testing with historical data or connection recovery.

## Configuration

`config.yaml` at project root:

```yaml
ibkr:
  host: "127.0.0.1"
  port: 7497          # 7497 for paper, 7496 for live
  client_id: 1

watchlist:
  - AAPL
  - TSLA
  - NVDA
  - SPY

market_data:
  bar_size: "5 secs"
  history_window: 100  # number of bars to keep

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
  stop_loss_pct: 2.0   # percent below entry

risk:
  max_position_value: 1000
  max_open_positions: 5
  daily_loss_limit: -500
```

## Project Structure

```
/Users/yavorradulov/dev/stock-trader/
├── config.yaml
├── pyproject.toml
├── src/
│   └── stock_trader/
│       ├── __init__.py
│       ├── main.py           # Entry point
│       ├── engine.py         # Orchestrator
│       ├── market_data.py    # IBKR streaming
│       ├── analysis.py       # Technical indicators
│       ├── strategy.py       # Signal generation
│       ├── execution.py      # Order placement & risk
│       └── cli.py            # Terminal UI
├── tests/
│   ├── test_analysis.py
│   ├── test_strategy.py
│   └── test_execution.py
└── README.md
```

## Dependencies

- `ib_insync` — IBKR connection & trading API
- `pandas` + `pandas_ta` — data handling & technical indicators
- `rich` — terminal UI
- `pyyaml` — configuration parsing
- `pytest` — testing

## Prerequisites

- IBKR account with paper trading enabled
- TWS or IB Gateway running locally on port 7497 (paper)
- API connections enabled in TWS/Gateway settings

## Future Extensions

- Web dashboard (FastAPI + React)
- Market scanner for dynamic ticker discovery
- Additional strategies (price action, ML-based)
- Live trading mode (switch port to 7496)
- Trade journaling and performance analytics
