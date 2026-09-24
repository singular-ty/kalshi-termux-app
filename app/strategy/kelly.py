"""Fractional Kelly criterion position sizing."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class KellyResult:
    full_kelly: float
    fractional_kelly: float
    allocation_usd: float
    kelly_pct_of_bankroll: float
    contracts: int
    edge: float
    expected_value_per_contract: float
    reason: str


def kelly_size(
    model_prob: float,
    contract_price: float,
    bankroll: float,
    fraction: float = 0.5,
    max_fraction: float = 0.05,
    payout_on_win: float = 1.0,
) -> KellyResult:
    """
    Binary contract Kelly.
    contract_price: dollars paid per contract (e.g. 0.20 for 20¢ YES).
    payout_on_win: dollars received if correct (typically $1.00 face).
    net odds b = (payout - price) / price
    """
    p = max(0.01, min(0.99, float(model_prob)))
    price = max(0.01, min(0.99, float(contract_price)))
    q = 1.0 - p
    win_profit = payout_on_win - price  # net dollars if win
    b = win_profit / price  # net fractional odds
    edge = p * payout_on_win - price  # EV per contract in dollars

    if b <= 0:
        return KellyResult(0, 0, 0, 0, 0, edge, edge, "Invalid odds (b<=0)")

    # f* = (b*p - q) / b
    full = (b * p - q) / b
    if full <= 0:
        return KellyResult(
            round(full, 6),
            0.0,
            0.0,
            0.0,
            0,
            round(edge, 4),
            round(edge, 4),
            "Negative edge — PASS",
        )

    frac = max(0.0, full * fraction)
    frac = min(frac, max_fraction)
    allocation = bankroll * frac
    contracts = int(allocation // price) if price > 0 else 0
    # spend only what contracts cost
    spend = contracts * price

    return KellyResult(
        full_kelly=round(full, 6),
        fractional_kelly=round(frac, 6),
        allocation_usd=round(spend, 2),
        kelly_pct_of_bankroll=round(frac * 100, 2),
        contracts=contracts,
        edge=round(edge, 4),
        expected_value_per_contract=round(edge, 4),
        reason="Sized" if contracts > 0 else "Edge positive but size rounds to 0",
    )
