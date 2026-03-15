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
