"""Keep the catalog current between deploys.

The catalog ships read-only inside the function (rebuilt locally and redeployed now and then). A weekly cron reads
the source's listings again and keeps what changed since in the collection database (Postgres when hosted):
new listings with their photos' visual embeddings, and new prices, stock and dates. Every change is also kept in
`listing_history`, so a listing going out of stock is a dated sale.

At startup the hosted API copies the shipped catalog to a writable temp file and applies the changes (open_catalog).
"""

import io
import json
import logging
import shutil
import sqlite3
import tempfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from PIL import Image

from app import db as catalog
from app import visual
from app.http import get_bytes

log = logging.getLogger(__name__)

PATCHED = Path(tempfile.gettempdir()) / "avers-catalog.sqlite"
TRACKED = ("price", "in_stock", "modified")  # a listing whose values differ here has changed


def refresh(catalog_db: sqlite3.Connection, store, listings: Iterable[tuple[dict, list]]) -> dict:
    """Keep every listing that is new or changed compared with the catalog in use. Returns counts."""
    known = {
        (r["source"], r["source_id"]): tuple(r[k] for k in TRACKED)
        for r in catalog_db.execute(f"SELECT source, source_id, {', '.join(TRACKED)} FROM coins")
    }
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    seen = new = changed = 0
    for coin, images in listings:
        seen += 1
        key = (coin["source"], coin["source_id"])
        state = tuple(coin.get(k) for k in TRACKED)
        if known.get(key) == state:
            continue
        is_new = key not in known
        new += is_new
        changed += not is_new
        coin = {k: v for k, v in coin.items() if k != "raw"}  # the source's full payload is not needed to serve
        vectors = _embed(images) if is_new else None
        store.save_catalog_update(key[0], key[1], json.dumps(coin), json.dumps(images), vectors, now)
        store.execute(
            "INSERT INTO listing_history (source, source_id, price, in_stock, seen_at) VALUES (?, ?, ?, ?, ?)",
            (key[0], key[1], coin.get("price"), coin.get("in_stock"), now),
        )
    log.warning("catalog refresh: %d listings read, %d new, %d changed", seen, new, changed)
    return {"seen": seen, "new": new, "changed": changed}


def _embed(images: list) -> bytes | None:
    """Visual embeddings of a new listing's photos, as the catalog index stores them (float32, one per image)."""
    if not visual.available() or not images:
        return None
    try:
        photos = [visual.square(Image.open(io.BytesIO(get_bytes(url, timeout=20)))) for _, url in images]
        return visual.embed(photos).astype(np.float32).tobytes()
    except Exception as e:  # a missing photo: the listing still counts, matched on facts alone
        log.warning("catalog refresh: no embedding (%s)", e)
        return None


def open_catalog(store) -> sqlite3.Connection:
    """The catalog to serve: the shipped one, or a temp copy with the changes kept since applied."""
    if not catalog.READ_ONLY:
        return catalog.connect()  # local catalog: the scraper updates it directly
    updates = store.query("SELECT coin, images, vectors FROM catalog_updates")
    if not updates:
        return catalog.connect()
    shutil.copyfile(catalog.DB_PATH, PATCHED)
    db = catalog.connect(PATCHED, read_only=False)
    for u in updates:
        images = [tuple(i) for i in json.loads(u["images"])]
        coin_id = catalog.upsert_coin(db, json.loads(u["coin"]), images)
        if u["vectors"] is not None:
            vectors = np.frombuffer(bytes(u["vectors"]), dtype=np.float32).reshape(-1, visual.DIM)
            db.execute("DELETE FROM coin_embeddings WHERE coin_id = ? AND model = ?", (coin_id, visual.MODEL))
            db.executemany(
                "INSERT INTO coin_embeddings VALUES (?, ?, ?, ?)",
                [(coin_id, n, visual.MODEL, v.tobytes()) for n, v in enumerate(vectors)],
            )
    db.commit()
    log.warning("catalog: %d updates applied", len(updates))
    return db
