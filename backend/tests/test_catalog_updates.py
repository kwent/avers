import json

from app import catalog_updates, collection
from app import db as catalog
from app.db import connect, upsert_coin


def listing(source_id, price, in_stock=1, modified="2026-10-01", name="FRANCE-1851A-10 Francs G. 1012 TTB"):
    coin = {
        "source": "gadoury",
        "source_id": source_id,
        "name": name,
        "country_iso": "FR",
        "year": 1851,
        "face_value": 10,
        "metal": "Or",
        "grade": "TTB",
        "price": price,
        "currency": "EUR",
        "in_stock": in_stock,
        "modified": modified,
        "raw": "{}",
    }
    return coin, [(0, f"https://example.com/{source_id}.jpg")]


def test_refresh_keeps_new_and_changed_listings_then_open_catalog_applies_them(tmp_path, monkeypatch):
    shipped = connect(tmp_path / "shipped.sqlite")
    coin, images = listing("1", 600)
    upsert_coin(shipped, coin, images)
    shipped.commit()
    store = collection.Store(sqlite_path=tmp_path / "collection.sqlite")

    counts = catalog_updates.refresh(
        shipped, store, [listing("1", 600), listing("1b", 650), listing("2", 900, in_stock=0, modified="2026-10-05")]
    )
    assert counts == {"seen": 3, "new": 2, "changed": 0}
    counts = catalog_updates.refresh(shipped, store, [listing("1", 640, in_stock=0, modified="2026-10-06")])
    assert counts == {"seen": 1, "new": 0, "changed": 1}  # sold: price and stock changed
    saved = {r["source_id"]: json.loads(r["coin"]) for r in store.query("SELECT * FROM catalog_updates")}
    assert set(saved) == {"1", "1b", "2"} and "raw" not in saved["1"]
    assert len(store.query("SELECT * FROM listing_history WHERE source_id = '1'")) == 1

    # the hosted API serves the shipped catalog with the changes applied
    monkeypatch.setattr(catalog, "READ_ONLY", True)
    monkeypatch.setattr(catalog, "DB_PATH", tmp_path / "shipped.sqlite")
    monkeypatch.setattr(catalog_updates, "PATCHED", tmp_path / "patched.sqlite")
    served = catalog_updates.open_catalog(store)
    rows = {r["source_id"]: r for r in served.execute("SELECT source_id, price, in_stock, gadoury FROM coins")}
    assert rows["1"]["price"] == 640 and rows["1"]["in_stock"] == 0
    assert set(rows) == {"1", "1b", "2"} and rows["2"]["gadoury"] == " 1012 "  # parsed when applied
