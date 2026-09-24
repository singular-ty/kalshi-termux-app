"""Order execution gate — DRY-RUN by default; live requires arm + typed confirm."""
from __future__ import annotations

import uuid
from typing import Any, Optional

from app.config import settings
from app.db.store import Store
from app.kalshi.client import KalshiClient


LIVE_CONFIRM_PHRASE = "ARM LIVE"


class OrderGate:
    def __init__(self, store: Store, client: Optional[KalshiClient] = None):
        self.store = store
        self.client = client or KalshiClient()
        self._live_armed = False

    @property
    def dry_run(self) -> bool:
        # Live only if env allows AND UI armed
        if settings.dry_run:
            return True
        return not self._live_armed

    @property
    def live_armed(self) -> bool:
        return self._live_armed and not settings.dry_run

    def status(self) -> dict:
        return {
            "env_dry_run": settings.dry_run,
            "live_armed": self._live_armed,
            "effective_mode": "DRY_RUN" if self.dry_run else "LIVE",
            "confirm_phrase": LIVE_CONFIRM_PHRASE,
            "has_keys": settings.has_keys,
        }

    def arm_live(self, confirm_phrase: str, totp_ok: bool = True) -> dict:
        if settings.dry_run:
            return {
                "ok": False,
                "error": "DRY_RUN=1 in environment. Set DRY_RUN=0 in .env and restart to allow live arming.",
            }
        if confirm_phrase.strip() != LIVE_CONFIRM_PHRASE:
            return {"ok": False, "error": f'Type exactly "{LIVE_CONFIRM_PHRASE}" to arm.'}
        if not totp_ok:
            return {"ok": False, "error": "TOTP verification failed."}
        if not settings.has_keys:
            return {"ok": False, "error": "API keys not configured."}
        self._live_armed = True
        self.store.log_activity("safety", "LIVE trading ARMED")
        return {"ok": True, "mode": "LIVE"}

    def disarm(self) -> dict:
        self._live_armed = False
        self.store.log_activity("safety", "Live trading DISARMED — back to dry-run gate")
        return {"ok": True, "mode": "DRY_RUN"}

    def place(
        self,
        ticker: str,
        side: str,
        count: int,
        price_cents: Optional[int] = None,
        coherence: Optional[float] = None,
        order_type: str = "limit",
    ) -> dict:
        side = side.lower().strip()
        if side not in {"yes", "no"}:
            return {"ok": False, "error": "side must be yes or no"}
        if count < 1:
            return {"ok": False, "error": "count must be >= 1"}

        client_order_id = str(uuid.uuid4())
        payload: dict[str, Any] = {
            "action": "buy",
            "client_order_id": client_order_id,
            "count": int(count),
            "side": side,
            "ticker": ticker,
            "type": order_type if price_cents is not None else "market",
        }
        if price_cents is not None and order_type == "limit":
            payload["yes_price" if side == "yes" else "no_price"] = int(price_cents)

        price = (price_cents / 100.0) if price_cents is not None else None

        if self.dry_run:
            oid = self.store.log_order(
                dry_run=True,
                ticker=ticker,
                side=side,
                count=count,
                price=price,
                status="DRY_RUN",
                coherence=coherence,
                payload=payload,
                response={"note": "Order NOT sent to Kalshi"},
            )
            msg = f"[DRY-RUN] Would BUY {count}x {side.upper()} {ticker}"
            self.store.log_activity("order", msg, payload)
            return {
                "ok": True,
                "dry_run": True,
                "order_log_id": oid,
                "message": msg,
                "payload": payload,
            }

        # LIVE
        try:
            resp = self.client.place_order(payload)
            oid = self.store.log_order(
                dry_run=False,
                ticker=ticker,
                side=side,
                count=count,
                price=price,
                status="SUBMITTED",
                coherence=coherence,
                payload=payload,
                response=resp,
            )
            msg = f"[LIVE] Submitted BUY {count}x {side.upper()} {ticker}"
            self.store.log_activity("order", msg, {"payload": payload, "response": resp})
            return {"ok": True, "dry_run": False, "order_log_id": oid, "response": resp, "message": msg}
        except Exception as e:
            oid = self.store.log_order(
                dry_run=False,
                ticker=ticker,
                side=side,
                count=count,
                price=price,
                status="ERROR",
                coherence=coherence,
                payload=payload,
                response={"error": str(e)},
            )
            self.store.log_activity("error", f"Live order failed: {e}", payload)
            return {"ok": False, "error": str(e), "order_log_id": oid}
