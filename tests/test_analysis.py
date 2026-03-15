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
