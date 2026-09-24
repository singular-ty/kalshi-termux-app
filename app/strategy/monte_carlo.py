"""Double-slit style Monte Carlo — honest probability collapse *simulation*.

This is NOT quantum mechanics applied to markets. It is a labeled Monte Carlo
interference-style noise model used to stress-test base probabilities.
"""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass


@dataclass
class SimResult:
    label: str
    base_prob: float
    collapsed_prob: float
    interference_factor: float
    nash_payoff: float
    payout_odds: float
    signal: str
    trials: int
    p05: float
    p50: float
    p95: float
    disclaimer: str


def double_slit_simulation(
    base_prob: float,
    payout_odds: float,
    trials: int = 2000,
    noise_sigma: float = 0.05,
    seed: int | None = None,
) -> SimResult:
    """
    Simulate many noisy observations of a binary event probability.
    'Interference' = multiplicative Gaussian noise around 1.0 (toy model).
    """
    rng = random.Random(seed)
    p0 = max(0.01, min(0.99, base_prob))
    samples = []
    for _ in range(max(50, trials)):
        interference = rng.gauss(1.0, noise_sigma)
        samples.append(max(0.01, min(0.99, p0 * interference)))

    samples.sort()
    collapsed = samples[len(samples) // 2]
    p05 = samples[int(0.05 * len(samples))]
    p95 = samples[int(0.95 * len(samples))]
    interference_factor = collapsed / p0 if p0 else 1.0

    # Expected net units if you pay 1/odds for a contract that pays 1 on win
    # Using odds as gross multiple (e.g. 5x means price ≈ 0.20)
    price = 1.0 / max(payout_odds, 1.01)
    nash_payoff = collapsed * payout_odds - (1.0 - collapsed) * 1.0
    # Alternative EV in dollars: collapsed * 1 - price
    ev = collapsed - price
    signal = "GO" if (nash_payoff > 0.25 and ev > 0.02) else "NO-GO"

    return SimResult(
        label="Monte Carlo probability-collapse simulation (not quantum magic)",
        base_prob=round(p0, 4),
        collapsed_prob=round(collapsed, 4),
        interference_factor=round(interference_factor, 4),
        nash_payoff=round(nash_payoff, 4),
        payout_odds=round(payout_odds, 2),
        signal=signal,
        trials=len(samples),
        p05=round(p05, 4),
        p50=round(collapsed, 4),
        p95=round(p95, 4),
        disclaimer=(
            "Simulation only. Does not predict real outcomes. "
            "No claim of guaranteed or 100% win rate."
        ),
    )


def sim_to_dict(r: SimResult) -> dict:
    return asdict(r)
