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
