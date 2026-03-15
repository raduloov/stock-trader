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
