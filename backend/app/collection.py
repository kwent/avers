"""The user's own collection and the photos behind it, kept apart from the catalog so re-imports never touch it.

Two backends with the same SQL: a local SQLite file (default, tests), or Postgres when DATABASE_URL is set (the
hosted API, where functions have no persistent disk). Photos live in the database too, so nothing is written to disk.
"""

import json
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.db import BACKEND, ROOT

log = logging.getLogger(__name__)

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

COMMON_TABLES = """
CREATE TABLE IF NOT EXISTS daily_usage (day TEXT PRIMARY KEY, estimates INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS api_cache (key TEXT PRIMARY KEY, data TEXT NOT NULL, fetched_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS counters (name TEXT PRIMARY KEY, n INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS photos_created ON photos (created_at);
"""
# Columns added after the first release: (table, column, sqlite type, postgres type)
ADDED_COLUMNS = [("photos", "thumb", "BLOB", "BYTEA"), ("photos", "embedding", "BLOB", "BYTEA")]
# Everything but the saved /estimate payload, for lists
ITEM_LIST_COLUMNS = "id, created_at, updated_at, " + ", ".join(
    line.split()[0] for line in ITEM_COLUMNS.strip().splitlines() if not line.strip().startswith("estimate")
)

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
  data BLOB NOT NULL,
  thumb BLOB,                     -- small JPEG for lists
  embedding BLOB                  -- visual query vectors (float32), so a re-price does not re-run the model
);
{COMMON_TABLES}"""

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
  data BYTEA NOT NULL,
  thumb BYTEA,
  embedding BYTEA
);
{COMMON_TABLES}"""

EDITABLE = {
    "title",
    "year",
    "denomination",
    "grade",
    "quantity",
    "value_low",
    "value_high",
    "notes",
}


SCAN_ONLY = {"year_check", "already_owned"}


class Store:
    """Collection storage. SQL is written with '?' placeholders; Postgres gets them rewritten to '%s'."""

    def __init__(self, database_url: str | None = None, sqlite_path: Path = COLLECTION_DB):
        self.postgres = bool(database_url)
        self._url = database_url
        self._lock = threading.Lock()
        self._pg = None  # one Postgres connection per instance, reused across requests (Fluid compute)
        if self.postgres:
            with self._db() as db:
                db.execute(POSTGRES_SCHEMA)
                for table, column, _, pg_type in ADDED_COLUMNS:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {pg_type}")
        else:
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            self._sqlite = sqlite3.connect(sqlite_path, check_same_thread=False)
            self._sqlite.row_factory = sqlite3.Row
            for table, column, sqlite_type, _ in ADDED_COLUMNS:  # before the schema: its index needs them
                if self._sqlite.execute(f"SELECT 1 FROM pragma_table_info('{table}')").fetchone():
                    known = {r["name"] for r in self._sqlite.execute(f"PRAGMA table_info({table})")}
                    if column not in known:
                        self._sqlite.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sqlite_type}")
            self._sqlite.executescript(SQLITE_SCHEMA)

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(self._url, autocommit=True, row_factory=dict_row, prepare_threshold=None)

    @contextmanager
    def _db(self):
        if self.postgres:
            with self._lock:
                if self._pg is None or self._pg.closed or self._pg.broken:
                    self._pg = self._connect()
                yield self._pg
        else:
            with self._lock:
                yield self._sqlite
                self._sqlite.commit()

    def _run(self, sql: str, params: tuple | list, fetch: bool) -> list[dict] | None:
        for attempt in (1, 2):
            try:
                with self._db() as db:
                    cur = db.execute(self._sql(sql), params)
                    return [dict(r) for r in cur.fetchall()] if fetch else None
            except Exception as e:
                # a connection the server dropped while idle: reconnect once (psycopg marks it closed/broken)
                if attempt == 2 or not self.postgres or not (self._pg is None or self._pg.closed or self._pg.broken):
                    raise
                log.warning("collection database connection lost, reconnecting: %s", e)
        return None

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.postgres else sql

    def query(self, sql: str, params: tuple | list = ()) -> list[dict]:
        return self._run(sql, params, fetch=True)

    def execute(self, sql: str, params: tuple | list = ()) -> None:
        self._run(sql, params, fetch=False)

    # --- items

    def add(self, estimate: dict, quantity: int = 1, notes: str | None = None) -> int:
        # what only mattered while scanning (the year question, "already owned") is not part of the saved coin
        estimate = {k: v for k, v in estimate.items() if k not in SCAN_ONLY}
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

    def set_estimate(self, item_id: int, estimate: dict) -> None:
        """A saved coin's new estimate (re-priced): its value and the facts the catalog settles. The title, year,
        grade, quantity and notes stay as the user kept them."""
        estimate = {k: v for k, v in estimate.items() if k not in SCAN_ONLY}
        coin, valuation = estimate["identification"], estimate.get("valuation") or {}
        self.execute(
            "UPDATE items SET estimate = ?, value_low = ?, value_high = ?, value_currency = ?, metal = ?,"
            " fineness = ?, weight_g = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (
                json.dumps(estimate, ensure_ascii=False),
                valuation.get("value_low"),
                valuation.get("value_high"),
                estimate["currency"],
                coin.get("metal"),
                coin.get("fineness"),
                coin.get("weight_g"),
                item_id,
            ),
        )

    def items(self) -> list[dict]:
        return self.query(f"SELECT {ITEM_LIST_COLUMNS} FROM items ORDER BY created_at DESC, id DESC")

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

    # --- usage

    def cached(self, key: str, max_age: timedelta) -> str | None:
        """A cached external API answer, if fetched within `max_age`."""
        cutoff = (datetime.now(UTC) - max_age).strftime("%Y-%m-%d %H:%M:%S")
        rows = self.query("SELECT data FROM api_cache WHERE key = ? AND fetched_at >= ?", (key, cutoff))
        return rows[0]["data"] if rows else None

    def cache(self, key: str, data: str) -> None:
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        self.execute(
            "INSERT INTO api_cache (key, data, fetched_at) VALUES (?, ?, ?)"
            " ON CONFLICT (key) DO UPDATE SET data = excluded.data, fetched_at = excluded.fetched_at",
            (key, data, now),
        )

    def bump(self, name: str) -> int:
        """Increment a named counter; returns its new value."""
        rows = self.query(
            "INSERT INTO counters (name, n) VALUES (?, 1)"
            " ON CONFLICT (name) DO UPDATE SET n = counters.n + 1 RETURNING n",
            (name,),
        )
        return int(rows[0]["n"])

    def count_estimate(self) -> int:
        """Record one estimate for today (UTC); returns today's total including this one."""
        day = datetime.now(UTC).strftime("%Y-%m-%d")
        rows = self.query(
            "INSERT INTO daily_usage (day, estimates) VALUES (?, 1)"
            " ON CONFLICT (day) DO UPDATE SET estimates = daily_usage.estimates + 1 RETURNING estimates",
            (day,),
        )
        return int(rows[0]["estimates"])

    # --- photos

    def put_photo(self, name: str, data: bytes, thumb: bytes | None = None) -> None:
        self.execute("INSERT INTO photos (name, data, thumb) VALUES (?, ?, ?)", (name, data, thumb))

    def set_embedding(self, name: str, vectors: bytes) -> None:
        self.execute("UPDATE photos SET embedding = ? WHERE name = ?", (vectors, name))

    def embedding(self, name: str) -> bytes | None:
        rows = self.query("SELECT embedding FROM photos WHERE name = ?", (name,))
        return bytes(rows[0]["embedding"]) if rows and rows[0]["embedding"] is not None else None

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

    def thumb(self, name: str) -> tuple[bytes | None, bytes | None]:
        """(small version, full photo): the full photo only when there is no small version yet."""
        sql = "SELECT thumb, CASE WHEN thumb IS NULL THEN data END AS data FROM photos WHERE name = ?"
        rows = self.query(sql, (name,))
        row = rows[0] if rows else {}
        return _bytes(row.get("thumb")), _bytes(row.get("data"))

    def set_thumb(self, name: str, thumb: bytes) -> None:
        self.execute("UPDATE photos SET thumb = ? WHERE name = ?", (thumb, name))


def _bytes(value) -> bytes | None:
    return bytes(value) if value is not None else None  # Postgres returns memoryview


def connect() -> Store:
    return Store(os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL"))
