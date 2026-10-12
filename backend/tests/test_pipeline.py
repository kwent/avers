from datetime import date

import pytest

from app import identify, main, pipeline
from app.db import upsert_coin
from tests.test_api import jpeg
from tests.test_catalog import make_coin

YEAR = date.today().year


@pytest.fixture
def catalog():
    """Two listings of the 1851 A in the shared test catalog, removed afterwards."""
    db = main.catalog_db
    ids = []
    for sid, grade, price in (("p1", "TTB", 600), ("p2", "SUP", 1000)):
        ids.append(
            upsert_coin(
                db,
                {
                    "source": "test",
                    "source_id": sid,
                    "name": f"FRANCE-1851A-10 Francs 2e République G. 1012 {grade}",
                    "url": f"https://example.com/{sid}",
                    "country_iso": "FR",
                    "year": 1851,
                    "face_value": 10,
                    "metal": "Or",
                    "weight_g": 3.22,
                    "grade": grade,
                    "price": price,
                    "currency": "EUR",
                    "in_stock": 1,
                    "modified": f"{YEAR}-01-01",
                },
                [],
            )
        )
    db.commit()
    yield ids
    db.execute(f"DELETE FROM coins WHERE id IN ({','.join('?' * len(ids))})", ids)
    db.commit()


def run(monkeypatch, catalog_ids, confidence=0.9, reading=None):
    seen = {}

    def fake_match(photos, candidates, coin, language):
        seen["candidates"] = [c["id"] for c in candidates]
        return identify.CatalogMatch(
            match_id=catalog_ids[0], same_coin_ids=catalog_ids, confidence=confidence, reason="same date and mint"
        )

    monkeypatch.setattr(identify, "identify", lambda images, language: reading or make_coin(year=1850, catalog_refs=[]))
    monkeypatch.setattr(identify, "match", fake_match)
    monkeypatch.setattr(identify, "market_quotes", lambda description: [])
    monkeypatch.setattr(identify, "explain", lambda context, language: "explained")
    photos = [(jpeg(), "f.jpg")]
    return pipeline.run(photos, "EUR", "fr", main.catalog_db, main.collection_db, None), seen


def test_catalog_entry_is_the_source_of_truth(monkeypatch, catalog):
    est, seen = run(monkeypatch, catalog)
    assert set(catalog) <= set(seen["candidates"])
    coin = est["identification"]
    assert coin["year"] == 1851  # Claude read 1850, the matched catalog entry says 1851
    assert coin["weight_g"] == 3.22
    assert "G. 1012" in coin["catalog_refs"]
    assert est["match"]["id"] == catalog[0]
    # prices from the two catalog listings: TTB 600 / SUP 1000 retail
    table = {r["grade"]: r for r in est["price_table"]}
    assert table["TTB"]["retail"] == 600
    assert table["SUP"]["retail"] == 1000
    assert est["valuation"]["retail_low"] == 600  # coin graded TTB: half a grade below = TTB itself
    assert est["valuation"]["explanation"] == "explained"


def test_unsure_match_is_ignored(monkeypatch, catalog):
    est, _ = run(monkeypatch, catalog, confidence=0.3)
    assert est["match"] is None
    assert est["identification"]["year"] == 1850  # Claude's reading is kept
    assert est["valuation"] is None  # no trustworthy market data -> no made-up price
