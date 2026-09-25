"""Kalshi Trade API v2 client — RSA-PSS auth + public endpoints.

Signature scheme ported from Operator's Gemini engine scraps:
  payload = f"{timestamp_ms}{METHOD}{path}{optional_body}"
  RSA-PSS SHA-256, salt_length=DIGEST_LENGTH, base64 signature.
"""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from app.config import settings
from app.kalshi.rate_limit import TokenBucketManager


class KalshiClient:
    def __init__(
        self,
        host: Optional[str] = None,
        key_id: Optional[str] = None,
        key_path: Optional[Path] = None,
        bucket: Optional[TokenBucketManager] = None,
    ):
        self.host = (host or settings.api_base).rstrip("/")
        self.key_id = key_id if key_id is not None else settings.key_id
        self.key_path = Path(key_path) if key_path else settings.key_path
        self.bucket = bucket or TokenBucketManager(tier="basic")
        self._session = requests.Session()
        self._private_key = None
        self.last_host_used = self.host
        self.last_error: Optional[str] = None

    # ----- crypto -----

    def _load_key(self):
        if self._private_key is not None:
            return self._private_key
        if not self.key_path.is_file():
            raise FileNotFoundError(f"API key file not found: {self.key_path}")
        with open(self.key_path, "rb") as f:
            self._private_key = serialization.load_pem_private_key(f.read(), password=None)
        return self._private_key

    def generate_signature(self, method: str, path: str, timestamp: str, body_str: str = "") -> str:
        private_key = self._load_key()
        # Kalshi signs path without query string for some endpoints;
        # use full path as passed (including query) — matches engine scraps.
        path_for_sig = path.split("?")[0]
        payload = f"{timestamp}{method.upper()}{path_for_sig}{body_str}"
        signature = private_key.sign(
            payload.encode("utf-8"),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("utf-8")

    def _auth_headers(self, method: str, path: str, body_str: str = "") -> dict:
        if not self.key_id:
            raise ValueError("KALSHI_KEY_ID not configured")
        ts = str(int(time.time() * 1000))
        sig = self.generate_signature(method, path, ts, body_str)
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-SIGNATURE": sig,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ----- transport -----

    def request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
        auth: bool = False,
        timeout: float = 12.0,
    ) -> dict[str, Any]:
        """Return parsed JSON or raise with useful context."""
        is_write = method.upper() in {"POST", "PUT", "DELETE", "PATCH"}
        if is_write:
            self.bucket.consume_write(1.0)
        else:
            self.bucket.consume_read(1.0)

        if not path.startswith("/"):
            path = "/" + path
        url = f"{self.host}{path}"
        body_str = json.dumps(json_body) if json_body is not None else ""
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if auth:
            # Sign path with query stripped (Kalshi RSA-PSS convention)
            headers = self._auth_headers(method, path, body_str)

        self.last_host_used = self.host
        self.last_error = None
        try:
            resp = self._session.request(
                method.upper(),
                url,
                headers=headers,
                params=params,
                data=body_str if body_str else None,
                timeout=timeout,
            )
        except requests.RequestException as e:
            self.last_error = str(e)
            raise RuntimeError(f"Network error contacting {self.host}: {e}") from e

        if resp.status_code >= 400:
            self.last_error = f"HTTP {resp.status_code}: {resp.text[:400]}"
            raise RuntimeError(self.last_error)

        if not resp.content:
            return {}
        return resp.json()

    def public_get(self, path: str, params: Optional[dict] = None) -> dict:
        return self.request("GET", path, params=params, auth=False)

    def auth_get(self, path: str, params: Optional[dict] = None) -> dict:
        return self.request("GET", path, params=params, auth=True)

    def auth_post(self, path: str, body: dict) -> dict:
        return self.request("POST", path, json_body=body, auth=True)

    # ----- public endpoints -----

    def exchange_status(self) -> dict:
        return self.public_get("/trade-api/v2/exchange/status")

    def get_markets(
        self,
        status: str = "open",
        limit: int = 100,
        cursor: Optional[str] = None,
        series_ticker: Optional[str] = None,
        ticker: Optional[str] = None,
        mve_filter: Optional[str] = "exclude",
    ) -> dict:
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        if cursor:
            params["cursor"] = cursor
        if series_ticker:
            params["series_ticker"] = series_ticker
        if ticker:
            params["ticker"] = ticker
        # Exclude multivariate/combo (CROSSCATEGORY) by default — otherwise the
        # open book is dominated by unpriced MVE legs.
        if mve_filter:
            params["mve_filter"] = mve_filter
        # Prefer public; fall back to auth if needed
        try:
            return self.public_get("/trade-api/v2/markets", params=params)
        except RuntimeError:
            if self.key_id and self.key_path.is_file():
                return self.auth_get("/trade-api/v2/markets", params=params)
            raise

    def get_events(
        self,
        series_ticker: str,
        status: str = "open",
        limit: int = 30,
        cursor: Optional[str] = None,
        with_nested_markets: bool = True,
    ) -> dict:
        """Open events for one series. Nested markets follow soonest-first."""
        params: dict[str, Any] = {
            "series_ticker": series_ticker,
            "limit": limit,
            "with_nested_markets": "true" if with_nested_markets else "false",
        }
        if status:
            params["status"] = status
        if cursor:
            params["cursor"] = cursor
        return self.public_get("/trade-api/v2/events", params=params)

    def get_market(self, ticker: str) -> dict:
        return self.public_get(f"/trade-api/v2/markets/{ticker}")

    def get_orderbook(self, ticker: str, depth: int = 10) -> dict:
        return self.public_get(
            f"/trade-api/v2/markets/{ticker}/orderbook",
            params={"depth": depth},
        )

    # ----- authenticated -----

    def get_balance(self) -> dict:
        return self.auth_get("/trade-api/v2/portfolio/balance")

    def get_positions(self, limit: int = 100) -> dict:
        return self.auth_get("/trade-api/v2/portfolio/positions", params={"limit": limit})

    def get_orders(self, status: Optional[str] = None, limit: int = 20) -> dict:
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        return self.auth_get("/trade-api/v2/portfolio/orders", params=params)

    def get_fills(self, limit: int = 20) -> dict:
        return self.auth_get("/trade-api/v2/portfolio/fills", params={"limit": limit})

    def place_order(self, order: dict) -> dict:
        return self.auth_post("/trade-api/v2/portfolio/orders", order)

    def ping(self) -> dict:
        """Lightweight connectivity check with host metadata."""
        data = self.exchange_status()
        return {
            "ok": True,
            "host": self.host,
            "host_key": settings.host_key,
            "exchange_active": data.get("exchange_active"),
            "trading_active": data.get("trading_active", data.get("exchange_active")),
            "raw": data,
            "authenticated": bool(self.key_id and self.key_path.is_file()),
        }
