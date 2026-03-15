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
