"""The user's own collection — kept in its own SQLite file so catalog re-imports never touch it."""

import json
import os
import sqlite3
from pathlib import Path

from app.db import ROOT

COLLECTION_DB = Path(os.environ.get("COLLECTION_DB", ROOT / "data" / "collection.sqlite"))
UPLOADS_DIR = Path(os.environ.get("UPLOADS_DIR", ROOT / "data" / "uploads"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
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
  photo_front TEXT,               -- file name in UPLOADS_DIR
  photo_back TEXT,
  notes TEXT,
  estimate JSON                   -- full /estimate payload at save time
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


def connect() -> sqlite3.Connection:
    COLLECTION_DB.parent.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(COLLECTION_DB, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def add(db: sqlite3.Connection, estimate: dict, quantity: int = 1, notes: str | None = None) -> int:
    coin = estimate["identification"]
    valuation = estimate.get("valuation") or {}
    cur = db.execute(
        "INSERT INTO items (title, country_iso, year, denomination, metal, fineness, weight_g, grade, quantity,"
        " value_low, value_high, value_currency, photo_front, photo_back, notes, estimate)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
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
        ),
    )
    db.commit()
    return cur.lastrowid


def update(db: sqlite3.Connection, item_id: int, fields: dict) -> None:
    fields = {k: v for k, v in fields.items() if k in EDITABLE}
    if not fields:
        return
    db.execute(
        f"UPDATE items SET {', '.join(f'{k} = ?' for k in fields)}, updated_at = datetime('now') WHERE id = ?",
        [*fields.values(), item_id],
    )
    db.commit()


def owned_count(db: sqlite3.Connection, country_iso: str | None, year: int | None, denomination: str | None) -> int:
    """How many of this coin (same country, year and denomination) are already in the collection."""
    if not (country_iso and year and denomination):
        return 0
    row = db.execute(
        "SELECT COALESCE(SUM(quantity), 0) FROM items"
        " WHERE country_iso = ? AND year = ? AND lower(denomination) = lower(?)",
        (country_iso, year, denomination),
    ).fetchone()
    return row[0]
