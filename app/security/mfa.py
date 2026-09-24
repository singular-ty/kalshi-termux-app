"""Local TOTP (Aegis-compatible) for app unlock / arm-live."""
from __future__ import annotations

import secrets
from typing import Optional

import pyotp


class TOTPManager:
    def __init__(self, vault=None):
        self.vault = vault

    def generate_secret(self) -> str:
        return pyotp.random_base32()

    def provisioning_uri(self, secret: str, account: str = "kalshi-termux") -> str:
        return pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name="KalshiPortal")

    def verify(self, secret: str, code: str, window: int = 1) -> bool:
        if not secret or not code:
            return False
        totp = pyotp.TOTP(secret)
        return bool(totp.verify(code.strip().replace(" ", ""), valid_window=window))

    def save_seed(self, secret: str) -> None:
        if not self.vault or not self.vault.unlocked:
            raise RuntimeError("Unlock vault before saving TOTP seed")
        self.vault.set("totp_secret", secret)

    def load_seed(self) -> Optional[str]:
        if not self.vault or not self.vault.unlocked:
            return None
        return self.vault.get("totp_secret")

    def has_seed(self) -> bool:
        try:
            return bool(self.load_seed())
        except Exception:
            return False
