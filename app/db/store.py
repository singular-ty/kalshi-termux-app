"""SQLite cache for market snapshots + activity / order log."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.config import settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else settings.db_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._lock:
            conn = self._conn()
            try:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS cache (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        ttl_seconds INTEGER NOT NULL DEFAULT 10
                    );
                    CREATE TABLE IF NOT EXISTS activity (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        message TEXT NOT NULL,
                        payload TEXT
                    );
                    CREATE TABLE IF NOT EXISTS orders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts TEXT NOT NULL,
                        dry_run INTEGER NOT NULL,
                        ticker TEXT NOT NULL,
                        side TEXT NOT NULL,
                        count INTEGER NOT NULL,
                        price REAL,
                        status TEXT NOT NULL,
                        coherence REAL,
                        payload TEXT,
                        response TEXT
                    );
                    CREATE TABLE IF NOT EXISTS settings_kv (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    """
                )
                conn.commit()
            finally:
                conn.close()

    def cache_get(self, key: str) -> Optional[Any]:
        with self._lock:
            conn = self._conn()
            try:
                row = conn.execute(
                    "SELECT value, updated_at, ttl_seconds FROM cache WHERE key=?",
                    (key,),
                ).fetchone()
                if not row:
                    return None
                updated = datetime.fromisoformat(row["updated_at"])
                age = (datetime.now(timezone.utc) - updated).total_seconds()
                if age > row["ttl_seconds"]:
                    return None
                return json.loads(row["value"])
            finally:
                conn.close()

    def cache_set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        ttl = ttl if ttl is not None else settings.cache_ttl
        with self._lock:
            conn = self._conn()
            try:
                conn.execute(
                    """
                    INSERT INTO cache(key, value, updated_at, ttl_seconds)
                    VALUES(?,?,?,?)
                    ON CONFLICT(key) DO UPDATE SET
                      value=excluded.value,
                      updated_at=excluded.updated_at,
                      ttl_seconds=excluded.ttl_seconds
                    """,
                    (key, json.dumps(value), _now(), ttl),
                )
                conn.commit()
            finally:
                conn.close()

    def log_activity(self, kind: str, message: str, payload: Any = None) -> None:
        with self._lock:
            conn = self._conn()
            try:
                conn.execute(
                    "INSERT INTO activity(ts, kind, message, payload) VALUES(?,?,?,?)",
                    (_now(), kind, message, json.dumps(payload) if payload is not None else None),
                )
                conn.commit()
            finally:
                conn.close()

    def recent_activity(self, limit: int = 50) -> list[dict]:
        with self._lock:
            conn = self._conn()
            try:
                rows = conn.execute(
                    "SELECT id, ts, kind, message, payload FROM activity ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                out = []
                for r in rows:
                    out.append(
                        {
                            "id": r["id"],
                            "ts": r["ts"],
                            "kind": r["kind"],
                            "message": r["message"],
                            "payload": json.loads(r["payload"]) if r["payload"] else None,
                        }
                    )
                return out
            finally:
                conn.close()

    def log_order(
        self,
        *,
        dry_run: bool,
        ticker: str,
        side: str,
        count: int,
        price: Optional[float],
        status: str,
        coherence: Optional[float] = None,
        payload: Any = None,
        response: Any = None,
    ) -> int:
        with self._lock:
            conn = self._conn()
            try:
                cur = conn.execute(
                    """
                    INSERT INTO orders(ts, dry_run, ticker, side, count, price, status, coherence, payload, response)
                    VALUES(?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        _now(),
                        1 if dry_run else 0,
                        ticker,
                        side,
                        count,
                        price,
                        status,
                        coherence,
                        json.dumps(payload) if payload is not None else None,
                        json.dumps(response) if response is not None else None,
                    ),
                )
                conn.commit()
                return int(cur.lastrowid)
            finally:
                conn.close()

    def recent_orders(self, limit: int = 50) -> list[dict]:
        with self._lock:
            conn = self._conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM orders ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._lock:
            conn = self._conn()
            try:
                row = conn.execute(
                    "SELECT value FROM settings_kv WHERE key=?", (key,)
                ).fetchone()
                return row["value"] if row else default
            finally:
                conn.close()

    def set_setting(self, key: str, value: str) -> None:
        with self._lock:
            conn = self._conn()
            try:
                conn.execute(
                    """
                    INSERT INTO settings_kv(key, value) VALUES(?,?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value
                    """,
                    (key, value),
                )
                conn.commit()
            finally:
                conn.close()
