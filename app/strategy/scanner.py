"""Scan open Kalshi markets for high-payout / mispriced single contracts."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from app.config import settings
from app.kalshi.client import KalshiClient
from app.strategy.kelly import kelly_size
from app.strategy.nash import nash_decision, nash_to_dict


def _cents_to_dollars(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        v = float(val)
    except (TypeError, ValueError):
        return None
    # Heuristic: values > 1 are likely cents (or dollars*100 integer)
    if v > 1.0:
        return v / 100.0
    return v


def _price_dollars(market: dict, side: str) -> Optional[float]:
    """Prefer *_dollars fields; fall back to integer cents fields."""
    side = side.lower()
    for key in (f"{side}_ask_dollars", f"{side}_bid_dollars"):
        if market.get(key) is not None:
            try:
                return float(market[key])
            except (TypeError, ValueError):
                pass
    for key in (f"{side}_ask", f"{side}_bid"):
        d = _cents_to_dollars(market.get(key))
        if d is not None:
            return d
    return None


def _payout_multiple(price: float) -> float:
    if price <= 0:
        return 0.0
    return 1.0 / price


def enrich_market(m: dict, bankroll: float = 1000.0) -> Optional[dict]:
    ticker = m.get("ticker") or ""
    if "CROSSCATEGORY" in ticker.upper():
        return None

    yes_ask = _price_dollars(m, "yes")
    no_ask = _price_dollars(m, "no")
    # Treat zero / missing asks as absent (common on empty combo books)
    if yes_ask is not None and yes_ask <= 0:
        yes_ask = None
    if no_ask is not None and no_ask <= 0:
        no_ask = None
    if yes_ask is None and no_ask is None:
        return None

    # Fill missing side from parity approx
    if yes_ask is None and no_ask is not None:
        yes_ask = max(0.01, min(0.99, 1.0 - no_ask))
    if no_ask is None and yes_ask is not None:
        no_ask = max(0.01, min(0.99, 1.0 - yes_ask))

    yes_ask = float(yes_ask)
    no_ask = float(no_ask)

    vol = float(m.get("volume") or m.get("volume_fp") or 0) or 0.0
    try:
        vol = float(vol)
    except (TypeError, ValueError):
        vol = 0.0
    oi = float(m.get("open_interest") or m.get("open_interest_fp") or 0) or 0.0
    try:
        oi = float(oi)
    except (TypeError, ValueError):
        oi = 0.0

    yes_bid = _price_dollars(m, "yes")  # approx; better: use bid fields
    # Try explicit bids
    yb = m.get("yes_bid_dollars")
    ya = m.get("yes_ask_dollars")
    try:
        if yb is not None and ya is not None:
            spread_cents = abs(float(ya) - float(yb)) * 100
        else:
            yb_c = m.get("yes_bid")
            ya_c = m.get("yes_ask")
            if yb_c is not None and ya_c is not None:
                spread_cents = abs(float(ya_c) - float(yb_c))
                if spread_cents < 1 and float(ya_c) <= 1:
                    spread_cents *= 100
            else:
                spread_cents = abs(yes_ask + no_ask - 1.0) * 100
    except (TypeError, ValueError):
        spread_cents = abs(yes_ask + no_ask - 1.0) * 100

    nash = nash_decision(
        yes_ask=yes_ask,
        no_ask=no_ask,
        spread_cents=spread_cents,
        volume=vol,
        open_interest=oi,
    )

    # Size the recommended side
    if nash.action == "BUY_YES":
        side_price = yes_ask
        model_p = nash.model_prob_yes
        side = "yes"
    elif nash.action == "BUY_NO":
        side_price = no_ask
        model_p = 1.0 - nash.model_prob_yes
        side = "no"
    else:
        side_price = min(yes_ask, no_ask)
        model_p = max(nash.model_prob_yes, 1.0 - nash.model_prob_yes)
        side = "pass"

    kelly = kelly_size(
        model_prob=model_p if side != "pass" else 0.5,
        contract_price=side_price,
        bankroll=bankroll,
        fraction=settings.kelly_fraction,
        max_fraction=settings.kelly_max_fraction,
    )

    yes_mult = _payout_multiple(yes_ask)
    no_mult = _payout_multiple(no_ask)
    best_mult = max(yes_mult, no_mult)
    cheap = (yes_ask * 100 <= settings.max_contract_price_cents) or (
        no_ask * 100 <= settings.max_contract_price_cents
    )
    high_payout = best_mult >= settings.min_payout_multiple

    return {
        "ticker": ticker,
        "title": m.get("title") or m.get("subtitle") or m.get("yes_sub_title") or ticker,
        "event_ticker": m.get("event_ticker"),
        "yes_ask": round(yes_ask, 4),
        "no_ask": round(no_ask, 4),
        "yes_ask_cents": round(yes_ask * 100, 1),
        "no_ask_cents": round(no_ask * 100, 1),
        "yes_payout_multiple": round(yes_mult, 2),
        "no_payout_multiple": round(no_mult, 2),
        "best_payout_multiple": round(best_mult, 2),
        "spread_cents": round(spread_cents, 2),
        "volume": vol,
        "open_interest": oi,
        "status": m.get("status"),
        "close_time": m.get("close_time"),
        "cheap_contract": cheap,
        "high_payout": high_payout,
        "nash": nash_to_dict(nash),
        "kelly": {
            "side": side,
            "full_kelly": kelly.full_kelly,
            "fractional_kelly": kelly.fractional_kelly,
            "allocation_usd": kelly.allocation_usd,
            "kelly_pct_of_bankroll": kelly.kelly_pct_of_bankroll,
            "contracts": kelly.contracts,
            "edge": kelly.edge,
            "expected_value_per_contract": kelly.expected_value_per_contract,
            "reason": kelly.reason,
        },
        "score": round(
            (nash.your_best_payoff * 10)
            + (nash.coherence * 2)
            + (0.5 if high_payout and cheap else 0)
            + min(1.0, (vol + oi) / 5000.0),
            4,
        ),
    }


def scan_opportunities(
    client: Optional[KalshiClient] = None,
    limit: Optional[int] = None,
    bankroll: float = 1000.0,
    only_actionable: bool = False,
) -> dict:
    client = client or KalshiClient()
    limit = limit or settings.scan_limit
    markets = []
    cursor = None
    pages = 0
    target = max(limit, 20)
    while len(markets) < target and pages < 5:
        raw = client.get_markets(
            status="open",
            limit=min(100, max(limit, 50)),
            cursor=cursor,
            mve_filter="exclude",
        )
        batch = raw.get("markets") or []
        markets.extend(batch)
        cursor = raw.get("cursor") or None
        pages += 1
        if not batch or not cursor:
            break
    markets = markets[: max(limit * 2, limit)]  # allow filter headroom
    enriched = []
    for m in markets:
        row = enrich_market(m, bankroll=bankroll)
        if not row:
            continue
        if only_actionable and row["nash"]["action"] == "PASS":
            # still keep high-payout cheap contracts for the scanner board
            if not (row["cheap_contract"] and row["high_payout"]):
                continue
        enriched.append(row)

    enriched.sort(key=lambda r: (r["score"], r["best_payout_multiple"]), reverse=True)
    now = datetime.now(timezone.utc).isoformat()
    return {
        "count": len(enriched),
        "scanned": len(markets),
        "host": client.host,
        "host_key": settings.host_key,
        "updated_at": now,
        "cache_ttl_seconds": settings.cache_ttl,
        "disclaimer": (
            "Edge and coherence are model estimates, not guarantees. "
            "No 100% win-rate claim. Risk of loss."
        ),
        "markets": enriched,
    }
