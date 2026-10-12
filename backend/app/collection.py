"""The user's own collection and the photos behind it, kept apart from the catalog so re-imports never touch it.

Two backends with the same SQL: a local SQLite file (default, tests), or Postgres when DATABASE_URL is set (the
hosted API, where functions have no persistent disk). Photos live in the database too, so nothing is written to disk.
"""

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.db import BACKEND, ROOT

COLLECTION_DB = BACKEND / os.environ.get("COLLECTION_DB", ROOT / "data" / "collection.sqlite")

ITEM_COLUMNS = """
  title TEXT NOT NULL,
  country_iso TEXT,
  year INTEGER,
  denomination TEXT,
  metal TEXT,
  fineness REAL,
  weight_g REAL,
  grade TEXT,
  quantity INTEGER NOT NULL DEFAULT 1,
  value_low REAL,
  value_high REAL,
  value_currency TEXT NOT NULL DEFAULT 'EUR',
  photo_front TEXT,               -- photos.name
  photo_back TEXT,
  notes TEXT,
  estimate TEXT                   -- full /estimate payload (JSON) at save time
"""

SQLITE_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  {ITEM_COLUMNS}
);
CREATE TABLE IF NOT EXISTS photos (
  name TEXT PRIMARY KEY,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  data BLOB NOT NULL
);
"""

POSTGRES_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS items (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  {ITEM_COLUMNS}
);
CREATE TABLE IF NOT EXISTS photos (
  name TEXT PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  data BYTEA NOT NULL
);
"""

EDITABLE = {
    "title",
    "year",
    "denomination",
    "grade",
    "quantity",
    "value_low",
    "value_high",
    "notes",
    "metal",
    "fineness",
    "weight_g",
}


class Store:
    """Collection storage. SQL is written with '?' placeholders; Postgres gets them rewritten to '%s'."""

    def __init__(self, database_url: str | None = None, sqlite_path: Path = COLLECTION_DB):
        self.postgres = bool(database_url)
        self._url = database_url
        self._lock = threading.Lock()
        if self.postgres:
            with self._connect() as db:
                db.execute(POSTGRES_SCHEMA)
        else:
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            self._sqlite = sqlite3.connect(sqlite_path, check_same_thread=False)
            self._sqlite.row_factory = sqlite3.Row
            self._sqlite.executescript(SQLITE_SCHEMA)

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(self._url, autocommit=True, row_factory=dict_row, prepare_threshold=None)

    @contextmanager
    def _db(self):
        if self.postgres:
            with self._connect() as db:
                yield db
        else:
            with self._lock:
                yield self._sqlite
                self._sqlite.commit()

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.postgres else sql

    def query(self, sql: str, params: tuple | list = ()) -> list[dict]:
        with self._db() as db:
            return [dict(r) for r in db.execute(self._sql(sql), params).fetchall()]

    def execute(self, sql: str, params: tuple | list = ()) -> None:
        with self._db() as db:
            db.execute(self._sql(sql), params)

    # --- items

    def add(self, estimate: dict, quantity: int = 1, notes: str | None = None) -> int:
        coin = estimate["identification"]
        valuation = estimate.get("valuation") or {}
        params = (
            coin["title"],
            coin.get("country_iso"),
            coin.get("year"),
            coin.get("denomination"),
            coin.get("metal"),
            coin.get("fineness"),
            coin.get("weight_g"),
            coin.get("grade"),
            quantity,
            valuation.get("value_low"),
            valuation.get("value_high"),
            estimate["currency"],
            estimate.get("photos", {}).get("front"),
            estimate.get("photos", {}).get("back"),
            notes,
            json.dumps(estimate, ensure_ascii=False),
        )
        sql = (
            "INSERT INTO items (title, country_iso, year, denomination, metal, fineness, weight_g, grade, quantity,"
            " value_low, value_high, value_currency, photo_front, photo_back, notes, estimate)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id"
        )
        return self.query(sql, params)[0]["id"]

    def items(self) -> list[dict]:
        return self.query("SELECT * FROM items ORDER BY created_at DESC, id DESC")

    def get(self, item_id: int) -> dict | None:
        rows = self.query("SELECT * FROM items WHERE id = ?", (item_id,))
        return rows[0] if rows else None

    def update(self, item_id: int, fields: dict) -> None:
        fields = {k: v for k, v in fields.items() if k in EDITABLE}
        if not fields:
            return
        self.execute(
            f"UPDATE items SET {', '.join(f'{k} = ?' for k in fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            [*fields.values(), item_id],
        )

    def delete(self, item_id: int) -> None:
        item = self.get(item_id)
        if not item:
            return
        self.execute("DELETE FROM items WHERE id = ?", (item_id,))
        for name in (item["photo_front"], item["photo_back"]):
            if name:
                self.execute("DELETE FROM photos WHERE name = ?", (name,))

    def owned_count(self, country_iso: str | None, year: int | None, denomination: str | None) -> int:
        """How many of this coin (same country, year and denomination) are already in the collection."""
        if not (country_iso and year and denomination):
            return 0
        rows = self.query(
            "SELECT COALESCE(SUM(quantity), 0) AS n FROM items"
            " WHERE country_iso = ? AND year = ? AND lower(denomination) = lower(?)",
            (country_iso, year, denomination),
        )
        return int(rows[0]["n"])

    # --- photos

    def put_photo(self, name: str, data: bytes) -> None:
        self.execute("INSERT INTO photos (name, data) VALUES (?, ?)", (name, data))

    def prune_photos(self, older_than: timedelta = timedelta(days=2)) -> None:
        """Forget photos of estimates that were never saved to the collection."""
        cutoff = (datetime.now(UTC) - older_than).strftime("%Y-%m-%d %H:%M:%S")
        self.execute(
            "DELETE FROM photos WHERE created_at < ? AND name NOT IN ("
            " SELECT photo_front FROM items WHERE photo_front IS NOT NULL"
            " UNION SELECT photo_back FROM items WHERE photo_back IS NOT NULL)",
            (cutoff,),
        )

    def photo(self, name: str) -> bytes | None:
        rows = self.query("SELECT data FROM photos WHERE name = ?", (name,))
        return bytes(rows[0]["data"]) if rows else None


def connect() -> Store:
    return Store(os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL"))
