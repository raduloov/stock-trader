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
