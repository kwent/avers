"""SQLite catalog shared by every price source (one dealer today, more later)."""

import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.environ.get("COINS_DB", ROOT / "data" / "coins.sqlite"))
IMAGES_DIR = Path(os.environ.get("COINS_IMAGES", ROOT / "data" / "images"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS coins (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,             -- e.g. 'gadoury'
  source_id TEXT NOT NULL,          -- id on the source site
  name TEXT,
  url TEXT,
  description TEXT,
  country_iso TEXT,                 -- ISO 3166-1 alpha-2
  year INTEGER,
  face_value REAL,
  metal TEXT,                       -- source wording (Gadoury: Or, Argent, ...)
  weight_g REAL,
  grade TEXT,                       -- source grading scale (Gadoury: French TB/TTB/SUP/FDC)
  category TEXT,
  price REAL,                       -- current asking / listed price
  original_price REAL,
  currency TEXT NOT NULL DEFAULT 'EUR',
  in_stock INTEGER,
  created TEXT,
  modified TEXT,
  raw JSON,
  UNIQUE (source, source_id)
);
CREATE TABLE IF NOT EXISTS coin_images (
  coin_id INTEGER NOT NULL REFERENCES coins(id) ON DELETE CASCADE,
  position INTEGER NOT NULL,
  url TEXT NOT NULL,
  local_path TEXT,                  -- relative to IMAGES_DIR once downloaded
  PRIMARY KEY (coin_id, position)
);
CREATE INDEX IF NOT EXISTS idx_coins_lookup ON coins(country_iso, year, face_value);
CREATE INDEX IF NOT EXISTS idx_coins_metal ON coins(metal);
"""


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")
    db.executescript(SCHEMA)
    return db


def upsert_coin(db: sqlite3.Connection, coin: dict, images: list[tuple[int, str]]) -> int:
    """Insert or update one coin (keyed on source + source_id) and replace its image list."""
    cols = list(coin)
    db.execute(
        f"INSERT INTO coins ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
        f"ON CONFLICT (source, source_id) DO UPDATE SET "
        + ", ".join(f"{c} = excluded.{c}" for c in cols if c not in ("source", "source_id")),
        [coin[c] for c in cols],
    )
    coin_id = db.execute(
        "SELECT id FROM coins WHERE source = ? AND source_id = ?", (coin["source"], coin["source_id"])
    ).fetchone()[0]
    existing = {r["position"]: r for r in db.execute("SELECT * FROM coin_images WHERE coin_id = ?", (coin_id,))}
    db.execute("DELETE FROM coin_images WHERE coin_id = ?", (coin_id,))
    for position, url in images:
        old = existing.get(position)
        # keep an already-downloaded file if the image URL did not change
        local = old["local_path"] if old is not None and old["url"] == url else None
        db.execute("INSERT INTO coin_images VALUES (?, ?, ?, ?)", (coin_id, position, url, local))
    return coin_id
