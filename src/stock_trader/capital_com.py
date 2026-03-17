"""
Capital.com REST API client for CFD trading.

Replaces ib_insync for market data and order execution.
Works on any OS (no Windows dependency).

Requires in .env:
  CAPITAL_API_KEY=your-api-key
  CAPITAL_EMAIL=your-email
  CAPITAL_PASSWORD=your-password
"""
import logging
import time
from collections import defaultdict
from datetime import datetime
from typing import Callable

import requests

from stock_trader.models import Bar

logger = logging.getLogger(__name__)

DEMO_BASE_URL = "https://demo-api-capital.backend-capital.com"
LIVE_BASE_URL = "https://api-capital.backend-capital.com"


class CapitalComClient:
    """Client for Capital.com REST API."""

    def __init__(
        self,
        api_key: str,
        email: str,
        password: str,
        demo: bool = True,
    ):
        self.api_key = api_key
        self.email = email
        self.password = password
        self.base_url = DEMO_BASE_URL if demo else LIVE_BASE_URL
        self.cst: str | None = None
        self.security_token: str | None = None
        self._last_auth: float = 0
        self._connected = False

    def connect(self) -> None:
        """Create a session with Capital.com."""
        resp = requests.post(
            f"{self.base_url}/api/v1/session",
            headers={"X-CAP-API-KEY": self.api_key},
            json={
                "identifier": self.email,
                "password": self.password,
                "encryptedPassword": False,
            },
        )
        resp.raise_for_status()

        self.cst = resp.headers.get("CST")
        self.security_token = resp.headers.get("X-SECURITY-TOKEN")
        self._last_auth = time.time()
        self._connected = True
        logger.info("Connected to Capital.com (%s)", "demo" if "demo" in self.base_url else "live")

    def disconnect(self) -> None:
        """Close the session."""
        if self._connected:
            try:
                self._request("DELETE", "/api/v1/session")
            except Exception:
                pass
            self._connected = False

    def isConnected(self) -> bool:
        return self._connected

    def _headers(self) -> dict:
        return {
            "X-CAP-API-KEY": self.api_key,
            "X-SECURITY-TOKEN": self.security_token or "",
            "CST": self.cst or "",
            "Content-Type": "application/json",
        }

    def _ensure_session(self) -> None:
        """Re-authenticate if session is about to expire (tokens last 10 min)."""
        if time.time() - self._last_auth > 8 * 60:  # refresh after 8 min
            self.connect()

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        self._ensure_session()
        resp = requests.request(
            method,
            f"{self.base_url}{path}",
            headers=self._headers(),
            **kwargs,
        )
        resp.raise_for_status()
        return resp

    # ---- Market Data ----

    def search_markets(self, query: str, limit: int = 5) -> list[dict]:
        """Search for instruments by name or symbol."""
        resp = self._request("GET", "/api/v1/markets", params={
            "searchTerm": query,
            "limit": limit,
        })
        return resp.json().get("markets", [])

    def get_prices(self, epic: str, resolution: str = "MINUTE", max_bars: int = 100) -> list[dict]:
        """Get historical price bars.

        resolution: MINUTE, MINUTE_5, MINUTE_15, MINUTE_30, HOUR, HOUR_4, DAY, WEEK
        """
        resp = self._request("GET", f"/api/v1/prices/{epic}", params={
            "resolution": resolution,
            "max": max_bars,
        })
        return resp.json().get("prices", [])

    def get_prices_for_date(self, epic: str, date_from: str, date_to: str, resolution: str = "MINUTE") -> list[dict]:
        """Get historical prices for a specific date range.

        date format: 2026-03-14T00:00:00
        """
        resp = self._request("GET", f"/api/v1/prices/{epic}", params={
            "resolution": resolution,
            "from": date_from,
            "to": date_to,
            "max": 1000,
        })
        return resp.json().get("prices", [])

    # ---- Trading ----

    def open_position(self, epic: str, direction: str, size: float, stop_distance: float | None = None) -> dict:
        """Open a new position.

        direction: "BUY" or "SELL"
        size: position size (number of contracts/units)
        """
        body = {
            "epic": epic,
            "direction": direction,
            "size": size,
        }
        if stop_distance is not None:
            body["stopDistance"] = stop_distance

        resp = self._request("POST", "/api/v1/positions", json=body)
        return resp.json()

    def close_position(self, deal_id: str) -> dict:
        """Close an existing position."""
        resp = self._request("DELETE", f"/api/v1/positions/{deal_id}")
        return resp.json()

    def get_positions(self) -> list[dict]:
        """Get all open positions."""
        resp = self._request("GET", "/api/v1/positions")
        return resp.json().get("positions", [])

    def get_accounts(self) -> list[dict]:
        """Get account info."""
        resp = self._request("GET", "/api/v1/accounts")
        return resp.json().get("accounts", [])

    def confirm_deal(self, deal_reference: str) -> dict:
        """Confirm a deal was executed."""
        resp = self._request("GET", f"/api/v1/confirms/{deal_reference}")
        return resp.json()


class CapitalComMarketData:
    """Market data manager using Capital.com API.
    Drop-in replacement for MarketDataManager (IBKR)."""

    def __init__(
        self,
        client: CapitalComClient,
        history_window: int = 100,
        poll_interval: int = 30,
        on_bar: Callable[[str, list[Bar]], None] | None = None,
    ):
        self.client = client
        self.history_window = history_window
        self.poll_interval = poll_interval
        self.resolution = "MINUTE_5"  # 5-min bars for strategy timeframe
        self.on_bar = on_bar
        self.bars: dict[str, list[Bar]] = defaultdict(list)
        self.epics: dict[str, str] = {}  # ticker -> Capital.com epic
        self._last_poll: float = 0

    @property
    def ib(self):
        """Compatibility shim so CLI can check connection status."""
        return self.client

    def connect(self) -> None:
        self.client.connect()

    def disconnect(self) -> None:
        self.client.disconnect()

    def subscribe(self, ticker: str) -> None:
        """Subscribe to a ticker. Looks up the Capital.com epic and fetches initial data."""
        if ticker not in self.epics:
            # First try exact match (ticker IS the epic)
            try:
                test_prices = self.client.get_prices(ticker, resolution="MINUTE", max_bars=1)
                if test_prices:
                    self.epics[ticker] = ticker
                    logger.info("Mapped %s -> %s (exact match)", ticker, ticker)
                    self._fetch_bars(ticker)
                    return
            except Exception:
                pass

            # Fall back to search
            markets = self.client.search_markets(ticker, limit=3)
            if markets:
                self.epics[ticker] = markets[0]["epic"]
                logger.info("Mapped %s -> %s (%s)", ticker, markets[0]["epic"], markets[0].get("instrumentName", ""))
            else:
                logger.warning("Could not find instrument for %s on Capital.com", ticker)
                return

        self._fetch_bars(ticker)

    def unsubscribe(self, ticker: str) -> None:
        self.epics.pop(ticker, None)
        self.bars.pop(ticker, None)

    def set_ticker_config(self, ticker: str, config) -> None:
        """Compatibility with engine — not needed for Capital.com."""
        pass

    def enable_polling_mode(self) -> None:
        """Always in polling mode for Capital.com."""
        pass

    def _fetch_bars(self, ticker: str) -> None:
        epic = self.epics.get(ticker)
        if not epic:
            return

        try:
            raw_prices = self.client.get_prices(epic, resolution=self.resolution, max_bars=self.history_window)
            if raw_prices:
                self.bars[ticker] = [self._parse_bar(p) for p in raw_prices]
                logger.info("Loaded %d bars for %s", len(self.bars[ticker]), ticker)
                if self.on_bar:
                    self.on_bar(ticker, self.bars[ticker])
            else:
                logger.warning("No price data for %s (%s)", ticker, epic)
        except Exception as e:
            logger.error("Failed to fetch prices for %s: %s", ticker, e)

    def poll_updates(self) -> None:
        """Poll for new data periodically."""
        now = time.time()
        if now - self._last_poll < self.poll_interval:
            return
        self._last_poll = now

        for ticker in list(self.epics.keys()):
            self._fetch_bars(ticker)

    def get_bars(self, ticker: str) -> list[Bar]:
        return self.bars.get(ticker, [])

    def sleep(self, seconds: float = 0) -> None:
        """Sleep and poll — no event loop like IBKR."""
        time.sleep(seconds)

    @staticmethod
    def _parse_bar(price_data: dict) -> Bar:
        """Parse a Capital.com price bar into our Bar model."""
        # Capital.com returns bid/ask prices; use mid-point
        bid = price_data.get("closePrice", {})
        ask = price_data.get("highPrice", {})

        # Simplified: use the close/open/high/low from the snapshot
        return Bar(
            timestamp=datetime.fromisoformat(price_data["snapshotTime"].replace("T", " ").split(".")[0]),
            open=float(price_data.get("openPrice", {}).get("bid", 0)),
            high=float(price_data.get("highPrice", {}).get("bid", 0)),
            low=float(price_data.get("lowPrice", {}).get("bid", 0)),
            close=float(price_data.get("closePrice", {}).get("bid", 0)),
            volume=int(price_data.get("lastTradedVolume", 0)),
        )
