"""SQLite catalog shared by every price source (one dealer today, more later)."""

import os
import sqlite3
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]  # relative paths in the environment are resolved from here
ROOT = BACKEND.parent  # repository root (local data/ lives there)
DB_PATH = BACKEND / os.environ.get("COINS_DB", ROOT / "data" / "coins.sqlite")
IMAGES_DIR = BACKEND / os.environ.get("COINS_IMAGES", ROOT / "data" / "images")

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


# Hosted API: the catalog ships inside the function, on a read-only disk.
READ_ONLY = os.environ.get("COINS_DB_READONLY") == "1"


def connect(path: Path = DB_PATH, read_only: bool = READ_ONLY) -> sqlite3.Connection:
    if read_only:
        db = sqlite3.connect(f"file:{path}?immutable=1", uri=True, check_same_thread=False)
        db.row_factory = sqlite3.Row
        return db
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


def export_slim(out: Path, src: Path = DB_PATH) -> None:
    """Copy of the catalog for the hosted API: what serving needs (no raw source payloads, no local image paths)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    db = sqlite3.connect(out)
    db.execute("ATTACH DATABASE ? AS src", (str(src),))
    db.executescript(SCHEMA)
    cols = [r[1] for r in db.execute("PRAGMA main.table_info(coins)") if r[1] != "raw"]
    db.execute(f"INSERT INTO coins ({', '.join(cols)}) SELECT {', '.join(cols)} FROM src.coins")
    db.execute("INSERT INTO coin_images (coin_id, position, url) SELECT coin_id, position, url FROM src.coin_images")
    has_embeddings = db.execute("SELECT 1 FROM src.sqlite_master WHERE name = 'coin_embeddings'").fetchone()
    if has_embeddings:
        db.execute("CREATE TABLE coin_embeddings AS SELECT * FROM src.coin_embeddings")
    db.commit()
    db.execute("DETACH DATABASE src")
    db.execute("VACUUM")
    db.close()
    print(f"wrote {out} ({out.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "export-slim":
        sys.exit("usage: python -m app.db export-slim OUT.sqlite")
    export_slim(Path(sys.argv[2]))
