import json
import os

import pytest

from app import collection
from tests.test_catalog import make_coin


@pytest.fixture(params=["sqlite", "postgres"])
def store(request, tmp_path):
    if request.param == "sqlite":
        return collection.Store(sqlite_path=tmp_path / "collection.sqlite")
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    s = collection.Store(url)
    s.execute("DELETE FROM items")
    s.execute("DELETE FROM photos")
    return s


def estimate(**coin):
    return {
        "currency": "EUR",
        "identification": make_coin(**coin).model_dump(),
        "valuation": {"value_low": 480, "value_high": 520},
        "photos": {"front": "f.jpg", "back": None},
    }


def test_items_roundtrip(store):
    store.put_photo("f.jpg", b"jpeg")
    item_id = store.add(estimate(), quantity=2, notes="héritage")
    assert store.get(item_id)["notes"] == "héritage"
    assert store.owned_count("FR", 1851, "10 francs") == 2

    store.update(item_id, {"quantity": 3, "title": "Cérès", "id": 99})  # id is not editable
    item = store.get(item_id)
    assert (item["id"], item["quantity"], item["title"]) == (item_id, 3, "Cérès")
    assert [i["id"] for i in store.items()] == [item_id]

    store.delete(item_id)
    assert store.get(item_id) is None and store.items() == []
    assert store.photo("f.jpg") is None  # photos go with the item


def test_photos_and_pruning(store):
    store.put_photo("kept.jpg", b"\x00\xffkept")
    store.put_photo("stale.jpg", b"stale")
    store.put_photo("fresh.jpg", b"fresh")
    store.add({**estimate(), "photos": {"front": "kept.jpg", "back": None}})
    store.execute("UPDATE photos SET created_at = '2000-01-01 00:00:00' WHERE name <> 'fresh.jpg'")
    store.prune_photos()
    assert store.photo("kept.jpg") == b"\x00\xffkept"  # saved in the collection
    assert store.photo("stale.jpg") is None  # old estimate never saved
    assert store.photo("fresh.jpg") == b"fresh"  # recent estimate, may still be saved


def test_daily_usage_counter(store):
    store.execute("DELETE FROM daily_usage")
    assert [store.count_estimate() for _ in range(3)] == [1, 2, 3]


def test_photo_thumbnail_and_query_vectors(store):
    store.put_photo("a.jpg", b"full", b"small")
    store.put_photo("b.jpg", b"full only")
    assert store.photo("a.jpg", thumb=True) == b"small"
    assert store.photo("a.jpg") == b"full"
    assert store.photo("b.jpg", thumb=True) == b"full only"  # older photos have no thumbnail
    assert store.embedding("a.jpg") is None
    store.set_embedding("a.jpg", b"\x01\x02")
    assert store.embedding("a.jpg") == b"\x01\x02"


def test_list_leaves_the_saved_estimate_out(store):
    store.add(estimate())
    assert "estimate" not in store.items()[0]


def test_postgres_reconnects_after_a_dropped_connection(store):
    if not store.postgres:
        pytest.skip("Postgres only")
    store.count_estimate()
    store._pg.close()  # what an idle connection closed by the server looks like
    assert store.query("SELECT 1 AS one") == [{"one": 1}]


def test_saved_coin_leaves_scan_only_fields_out(store):
    item_id = store.add({**estimate(), "year_check": {"read": 1861, "suggestions": [1851]}, "already_owned": 2})
    saved = json.loads(store.get(item_id)["estimate"])
    assert "year_check" not in saved and "already_owned" not in saved
