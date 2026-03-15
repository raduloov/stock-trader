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
