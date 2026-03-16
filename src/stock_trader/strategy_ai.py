"""
AI-powered trading strategy using LLMs to analyze market data
and make trading decisions.

Supports:
- Gemini (free tier): set GEMINI_API_KEY env var
- Claude: set ANTHROPIC_API_KEY env var

Uses Gemini by default (free). Falls back to Claude if only ANTHROPIC_API_KEY is set.
"""
import json
import logging
import os
import time
from typing import Any

from stock_trader.config import StrategyConfig
from stock_trader.models import Bar, IndicatorResult, Signal

logger = logging.getLogger(__name__)

# Rate limit: don't call the API more than once per ticker per N seconds
_MIN_INTERVAL = 10
_last_call: dict[str, float] = {}
# In backtest mode, rate limit by bar count instead of wall clock
_last_bar_count: dict[str, int] = {}
_BAR_INTERVAL = 30  # analyze every 30 bars in backtest (~30 minutes of 1-min bars)


def _build_prompt(market_data: dict) -> str:
    return f"""You are a day trading analyst. Analyze this market data and decide whether to BUY, SELL, or HOLD.

MARKET DATA:
{json.dumps(market_data, indent=2)}

RULES:
- You are day trading (positions opened and closed same day)
- Only recommend BUY if you see a clear entry opportunity
- Only recommend SELL if we currently hold this stock (currently_holding=true) and should exit
- If we don't hold the stock, SELL means "don't buy / avoid"
- HOLD means no action needed right now
- Be decisive — avoid HOLD if there's a clear signal
- Consider: trend direction, momentum, support/resistance levels, volume

Respond with ONLY valid JSON (no markdown, no explanation outside JSON):
{{"action": "BUY"|"SELL"|"HOLD", "confidence": 0.0-1.0, "reason": "brief explanation"}}"""


def _call_gemini(prompt: str) -> str:
    """Call Google Gemini API."""
    from google import genai

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
    )
    return response.text.strip()


def _call_claude(prompt: str) -> str:
    """Call Anthropic Claude API."""
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=150,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def _get_provider() -> str:
    """Determine which AI provider to use based on available keys."""
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude"
    return "none"


def evaluate_ai(
    indicators: IndicatorResult,
    bars: list[Bar],
    config: StrategyConfig,
    positions: dict[str, Any] | None = None,
    backtest: bool = False,
) -> Signal:
    """Use an LLM to analyze market data and produce a trading signal."""

    # Skip if insufficient data
    if indicators.close is None or len(bars) < 20:
        return Signal(
            ticker=indicators.ticker,
            action="HOLD",
            confidence=0.0,
            reason="Insufficient data for AI analysis",
        )

    # Rate limit — don't spam the API
    if backtest:
        bar_count = len(bars)
        last_count = _last_bar_count.get(indicators.ticker, 0)
        if bar_count - last_count < _BAR_INTERVAL:
            return Signal(
                ticker=indicators.ticker,
                action="HOLD",
                confidence=0.0,
                reason="Waiting for next analysis window",
            )
        _last_bar_count[indicators.ticker] = bar_count
    else:
        now = time.time()
        last = _last_call.get(indicators.ticker, 0)
        if now - last < _MIN_INTERVAL:
            return Signal(
                ticker=indicators.ticker,
                action="HOLD",
                confidence=0.0,
                reason="Waiting for next analysis window",
            )
        _last_call[indicators.ticker] = now

    # Build market context
    recent_bars = bars[-20:]
    prices = [b.close for b in recent_bars]
    volumes = [b.volume for b in recent_bars]

    price_change_pct = (prices[-1] - prices[0]) / prices[0] * 100 if prices[0] else 0
    high = max(b.high for b in recent_bars)
    low = min(b.low for b in recent_bars)

    has_position = indicators.ticker in (positions or {})

    market_data = {
        "ticker": indicators.ticker,
        "current_price": indicators.close,
        "price_20_bars_ago": prices[0],
        "price_change_pct": round(price_change_pct, 2),
        "high_20_bars": round(high, 2),
        "low_20_bars": round(low, 2),
        "recent_prices": [round(p, 2) for p in prices[-10:]],
        "recent_volumes": volumes[-10:],
        "indicators": {
            "rsi": round(indicators.rsi, 1) if indicators.rsi else None,
            "sma_20": round(indicators.sma, 2) if indicators.sma else None,
            "ema_12": round(indicators.ema, 2) if indicators.ema else None,
            "macd": round(indicators.macd, 4) if indicators.macd else None,
            "macd_signal": round(indicators.macd_signal, 4) if indicators.macd_signal else None,
            "macd_histogram": round(indicators.macd_hist, 4) if indicators.macd_hist else None,
            "bollinger_upper": round(indicators.bb_upper, 2) if indicators.bb_upper else None,
            "bollinger_middle": round(indicators.bb_middle, 2) if indicators.bb_middle else None,
            "bollinger_lower": round(indicators.bb_lower, 2) if indicators.bb_lower else None,
        },
        "currently_holding": has_position,
    }

    prompt = _build_prompt(market_data)
    provider = _get_provider()

    try:
        if provider == "gemini":
            text = _call_gemini(prompt)
        elif provider == "claude":
            text = _call_claude(prompt)
        else:
            return Signal(
                ticker=indicators.ticker,
                action="HOLD",
                confidence=0.0,
                reason="No AI API key configured (set GEMINI_API_KEY or ANTHROPIC_API_KEY)",
            )

        # Clean response — strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        # Parse JSON response
        result = json.loads(text)
        action = result.get("action", "HOLD").upper()
        confidence = float(result.get("confidence", 0.0))
        reason = result.get("reason", "AI analysis")

        # Validate action
        if action not in ("BUY", "SELL", "HOLD"):
            action = "HOLD"
            confidence = 0.0

        logger.info("AI [%s] signal for %s: %s (%.0f%%) — %s",
                     provider, indicators.ticker, action, confidence * 100, reason)

        return Signal(
            ticker=indicators.ticker,
            action=action,
            confidence=confidence,
            reason=f"AI: {reason}",
        )

    except Exception as e:
        logger.error("AI [%s] error for %s: %s", provider, indicators.ticker, e)
        return Signal(
            ticker=indicators.ticker,
            action="HOLD",
            confidence=0.0,
            reason=f"AI error: {type(e).__name__}: {str(e)[:60]}",
        )
