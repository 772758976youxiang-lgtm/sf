"""Local, short-lived mapping from SF waybills to customer order IDs."""

from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
import time


RETENTION_SECONDS = 24 * 60 * 60


def default_path() -> Path:
    configured = os.getenv("SF_ORDER_MAP_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.getenv("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return base / "sf-express-mcp" / "order-map.sqlite3"


class OrderMap:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_path()

    @staticmethod
    def _account_key(partner_id: str) -> str:
        return hashlib.sha256(partner_id.encode("utf-8")).hexdigest()

    @staticmethod
    def _initialize(db: sqlite3.Connection) -> None:
        db.execute("""
            CREATE TABLE IF NOT EXISTS order_map (
                environment TEXT NOT NULL,
                account_key TEXT NOT NULL,
                waybill_number TEXT NOT NULL,
                order_id TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                PRIMARY KEY (environment, account_key, waybill_number)
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS order_map_expires_at ON order_map(expires_at)")

    def save(self, environment: str, partner_id: str, order_id: str, waybills: list[str], *, now: int | None = None) -> None:
        if not waybills:
            return
        current = int(time.time()) if now is None else now
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            self._initialize(db)
            db.execute("DELETE FROM order_map WHERE expires_at <= ?", (current,))
            db.executemany("""
                INSERT INTO order_map (environment, account_key, waybill_number, order_id, expires_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(environment, account_key, waybill_number)
                DO UPDATE SET order_id = excluded.order_id, expires_at = excluded.expires_at
            """, [
                (environment, self._account_key(partner_id), number, order_id, current + RETENTION_SECONDS)
                for number in waybills
            ])

    def lookup(self, environment: str, partner_id: str, waybill_number: str, *, now: int | None = None) -> str | None:
        if not self.path.exists():
            return None
        current = int(time.time()) if now is None else now
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            self._initialize(db)
            db.execute("DELETE FROM order_map WHERE expires_at <= ?", (current,))
            row = db.execute("""
                SELECT order_id FROM order_map
                WHERE environment = ? AND account_key = ? AND waybill_number = ? AND expires_at > ?
            """, (environment, self._account_key(partner_id), waybill_number, current)).fetchone()
            return row[0] if row else None


def remember_created_order(config, result: dict) -> dict:
    """Persist successful order mappings without hiding a created order on disk failure."""
    if result.get("status") != "created" or not result.get("waybill_numbers"):
        return result
    try:
        OrderMap().save(config.environment, config.partner_id, result["order_id"], result["waybill_numbers"])
        result["mapping_saved"] = True
    except (OSError, sqlite3.Error):
        result["mapping_saved"] = False
    return result


def find_order_id(config, tracking_type: str, tracking_number: str) -> str | None:
    if tracking_type == "order":
        return tracking_number
    try:
        return OrderMap().lookup(config.environment, config.partner_id, tracking_number)
    except (OSError, sqlite3.Error):
        return None
