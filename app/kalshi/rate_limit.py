"""Independent read/write token-bucket rate limiter (ported from engine scraps)."""
from __future__ import annotations

import threading
import time


class TokenBucketManager:
    """Prevents 429 throttling with separate read/write budgets."""

    TIERS = {
        "basic": {"read": 20, "write": 10},
        "advanced": {"read": 30, "write": 20},
        "premier": {"read": 80, "write": 40},
    }

    def __init__(self, tier: str = "basic"):
        cfg = self.TIERS.get(tier, self.TIERS["basic"])
        # tokens per second ≈ cfg value / 10 (conservative for Termux)
        self.read_rate = cfg["read"] / 10.0
        self.write_rate = cfg["write"] / 10.0
        self.read_tokens = float(cfg["read"])
        self.write_tokens = float(cfg["write"])
        self.max_read = float(cfg["read"]) * 2
        self.max_write = float(cfg["write"]) * 2
        self.last_refill = time.time()
        self._lock = threading.Lock()

    def refill(self) -> None:
        now = time.time()
        delta = now - self.last_refill
        self.last_refill = now
        self.read_tokens = min(self.max_read, self.read_tokens + delta * self.read_rate)
        self.write_tokens = min(self.max_write, self.write_tokens + delta * self.write_rate)

    def consume_read(self, cost: float = 1.0, block: bool = True) -> bool:
        with self._lock:
            self.refill()
            if self.read_tokens >= cost:
                self.read_tokens -= cost
                return True
            if not block:
                return False
            need = cost - self.read_tokens
            wait = need / max(self.read_rate, 0.01)
        time.sleep(min(wait, 2.0))
        return self.consume_read(cost, block=False) or self.consume_read(cost, block=True)

    def consume_write(self, cost: float = 1.0, block: bool = True) -> bool:
        with self._lock:
            self.refill()
            if self.write_tokens >= cost:
                self.write_tokens -= cost
                return True
            if not block:
                return False
            need = cost - self.write_tokens
            wait = need / max(self.write_rate, 0.01)
        time.sleep(min(wait, 3.0))
        return self.consume_write(cost, block=False) or self.consume_write(cost, block=True)

    def status(self) -> dict:
        with self._lock:
            self.refill()
            return {
                "read_tokens": round(self.read_tokens, 1),
                "write_tokens": round(self.write_tokens, 1),
                "max_read": self.max_read,
                "max_write": self.max_write,
            }
