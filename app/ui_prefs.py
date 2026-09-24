"""Saved trading-mode choice. Lives under data/ (gitignored). No secrets."""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from app.config import settings


def prefs_path():
    return settings.data_dir / "ui_prefs.json"


def _as_bool(val: Any) -> Optional[bool]:
    if isinstance(val, bool):
        return val
    if isinstance(val, int) and val in (0, 1):
        return bool(val)
    if isinstance(val, str):
        low = val.strip().lower()
        if low in {"1", "true", "yes", "on"}:
            return True
        if low in {"0", "false", "no", "off"}:
            return False
    return None


def _read_file() -> Optional[bool]:
    path = prefs_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    if not isinstance(data, dict) or "dry_run" not in data:
        return None
    return _as_bool(data.get("dry_run"))


def load_dry_run_override(store=None) -> Optional[bool]:
    """Return saved paper flag, or None when the user has never chosen."""
    file_val = _read_file()
    if file_val is not None:
        return file_val
    if store is not None:
        raw = store.get_setting("dry_run")
        if raw is not None:
            return _as_bool(raw)
    return None


def save_dry_run_override(dry_run: bool, store=None) -> None:
    settings.ensure_dirs()
    path = prefs_path()
    data: dict = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, json.JSONDecodeError, UnicodeError):
            data = {}
    data["dry_run"] = bool(dry_run)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    if store is not None:
        store.set_setting("dry_run", "1" if dry_run else "0")


def clear_dry_run_override(store=None) -> None:
    path = prefs_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        data.pop("dry_run", None)
        if data:
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        else:
            path.unlink(missing_ok=True)
    if store is not None:
        store.delete_setting("dry_run")


def apply_saved_mode(store=None) -> None:
    """Env DRY_RUN is the boot default only when nothing has been saved."""
    override = load_dry_run_override(store)
    if override is None:
        settings.dry_run = bool(settings.env_dry_run)
        return
    settings.dry_run = override
    if store is not None:
        store.set_setting("dry_run", "1" if override else "0")
    if _read_file() is None:
        save_dry_run_override(override, store=None)
