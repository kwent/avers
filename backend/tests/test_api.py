import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import identify, main
from tests.test_catalog import make_coin

client = TestClient(main.app)


def jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (2400, 1800), "goldenrod").save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture
def fake_vision(monkeypatch):
    calls = {}

    def fake_identify(images, language):
        calls["language"] = language
        return make_coin()

    monkeypatch.setattr(identify, "identify", fake_identify)
    return calls


def test_health():
    assert client.get("/health").json()["ok"] is True


def test_estimate_then_collection_roundtrip(fake_vision, catalog_1851):
    res = client.post(
        "/estimate",
        files={"front": ("f.jpg", jpeg(), "image/jpeg"), "back": ("b.jpg", jpeg(), "image/jpeg")},
        data={"currency": "EUR"},
    )
    assert res.status_code == 200, res.text
    est = res.json()
    assert est["identification"]["year"] == 1851
    assert est["melt"]["metal"] == "gold"
    # coin graded TTB; catalog lists TTB 600 € / SUP 1000 € -> TTB retail 600, private resale 80%
    assert est["valuation"]["retail_low"] == 600
    assert est["valuation"]["value_low"] == 480
    assert est["already_owned"] == 0

    # uploaded photo is downsized and served back
    photo = client.get(f"/uploads/{est['photos']['front']}")
    assert photo.status_code == 200
    assert max(Image.open(io.BytesIO(photo.content)).size) <= main.MAX_SIDE

    item = client.post("/collection", json={"estimate": est, "quantity": 2}).json()
    client.patch(f"/collection/{item['id']}", json={"quantity": 3, "notes": "héritage"})

    col = client.get("/collection", params={"currency": "EUR"}).json()
    assert col["totals"]["count"] == 3
    assert col["totals"]["value_low"] == 3 * 480
    assert col["totals"]["melt"] > 0

    # scanning the same coin again warns that it is already owned
    again = client.post("/estimate", files={"front": ("f.jpg", jpeg(), "image/jpeg")}).json()
    assert again["already_owned"] == 3

    assert client.delete(f"/collection/{item['id']}").json() == {"ok": True}
    assert client.get(f"/collection/{item['id']}").status_code == 404


def test_estimate_rejects_non_image():
    res = client.post("/estimate", files={"front": ("f.jpg", b"not an image", "image/jpeg")})
    assert res.status_code == 400


def test_token_required_when_configured(monkeypatch):
    monkeypatch.setattr(main, "APP_TOKEN", "secret")
    assert client.get("/collection").status_code == 401
    assert client.get("/collection", headers={"X-App-Token": "secret"}).status_code == 200
    assert client.get("/health").status_code == 200  # uptime checks need no secret


@pytest.mark.parametrize("sent,used", [("en", "en"), ("fr", "fr"), ("xx", "fr")])
def test_estimate_language(fake_vision, sent, used):
    res = client.post("/estimate", files={"front": ("f.jpg", jpeg(), "image/jpeg")}, data={"language": sent})
    assert res.json()["language"] == used
    assert fake_vision["language"] == used


def test_prompts_name_the_language():
    assert "in English" in identify.IDENTIFY_PROMPT.format(language=identify.language_name("en"))
    assert identify.language_name("de") == "French"  # unsupported -> default


@pytest.mark.parametrize("status", ["not_a_coin", "unidentifiable"])
def test_estimate_never_values_what_it_cannot_identify(monkeypatch, status):
    monkeypatch.setattr(identify, "identify", lambda images, language: make_coin(status=status, title=""))
    est = client.post("/estimate", files={"front": ("f.jpg", jpeg(), "image/jpeg")}).json()
    assert est["identification"]["status"] == status
    assert est["valuation"] is None and est["melt"] is None and est["comparables"] == []


def test_low_confidence_is_downgraded():
    coin = identify.enforce_confidence(make_coin(confidence=0.3))
    assert coin.status == "unidentifiable"
    assert identify.enforce_confidence(make_coin(confidence=0.9)).status == "identified"


@pytest.mark.parametrize(
    "sides,swapped,warning",
    [
        (["obverse", "reverse"], False, None),
        (["reverse", "obverse"], True, None),
        (["obverse", "obverse"], False, "same_side"),
        (["unclear", "unclear"], False, None),
    ],
)
def test_photo_sides(fake_vision, monkeypatch, sides, swapped, warning):
    monkeypatch.setattr(identify, "identify", lambda images, language: make_coin(photo_sides=sides))
    est = client.post(
        "/estimate",
        files={"front": ("f.jpg", jpeg(), "image/jpeg"), "back": ("b.jpg", jpeg(), "image/jpeg")},
    ).json()
    assert est["photo_warning"] == warning
    front, back = (r["name"] for r in main.store.query("SELECT name FROM photos ORDER BY rowid DESC LIMIT 2")[::-1])
    assert (est["photos"]["front"], est["photos"]["back"]) == ((back, front) if swapped else (front, back))
    assert est["photos"]["swapped"] is swapped


def test_photos_are_served_without_the_token_and_pruned(monkeypatch, fake_vision):
    monkeypatch.setattr(main, "APP_TOKEN", "secret")
    est = client.post(
        "/estimate", files={"front": ("f.jpg", jpeg(), "image/jpeg")}, headers={"X-App-Token": "secret"}
    ).json()
    name = est["photos"]["front"]
    assert client.get(f"/uploads/{name}").status_code == 200  # image views send no header
    assert client.get("/collection").status_code == 401  # everything else still needs it

    main.store.execute("UPDATE photos SET created_at = '2000-01-01 00:00:00' WHERE name = ?", (name,))
    main.store.prune_photos()
    assert client.get(f"/uploads/{name}").status_code == 404  # never saved -> forgotten


def test_saved_photos_survive_pruning(fake_vision, catalog_1851):
    est = client.post("/estimate", files={"front": ("f.jpg", jpeg(), "image/jpeg")}).json()
    item = client.post("/collection", json={"estimate": est}).json()
    main.store.execute("UPDATE photos SET created_at = '2000-01-01 00:00:00'")
    main.store.prune_photos()
    assert client.get(f"/uploads/{est['photos']['front']}").status_code == 200
    client.delete(f"/collection/{item['id']}")
    assert client.get(f"/uploads/{est['photos']['front']}").status_code == 404  # deleted with the item


def test_cors_preflight_for_the_web_app(monkeypatch):
    from fastapi.middleware.cors import CORSMiddleware

    app = main.FastAPI(dependencies=[main.Depends(main.check_token)])
    app.add_middleware(
        CORSMiddleware, allow_origins=["https://avers.example"], allow_methods=["*"], allow_headers=["*"]
    )
    app.get("/health")(main.health)
    monkeypatch.setattr(main, "APP_TOKEN", "secret")
    res = TestClient(app).options(
        "/health",
        headers={
            "Origin": "https://avers.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-app-token",
        },
    )
    assert res.status_code == 200 and res.headers["access-control-allow-origin"] == "https://avers.example"


def test_daily_estimate_limit(monkeypatch, fake_vision):
    monkeypatch.setattr(main, "MAX_ESTIMATES_PER_DAY", main.store.count_estimate() + 1)  # one more allowed today
    post = lambda: client.post("/estimate", files={"front": ("f.jpg", jpeg(), "image/jpeg")})  # noqa: E731
    assert post().status_code == 200
    assert post().status_code == 429


def test_misread_year_asks_the_user_then_reprices(monkeypatch, catalog_1851):
    """A worn 1851 read as 1861: no listing, so the app is asked to check the year; the user's year re-prices it."""
    monkeypatch.setattr(
        identify, "identify", lambda images, language: make_coin(year=1861, title="10 Francs Cérès 1861 A")
    )
    est = client.post("/estimate", files={"front": ("f.jpg", jpeg(), "image/jpeg")}).json()
    assert est["valuation"] is None
    assert est["year_check"] == {"read": 1861, "suggestions": [1851]}

    fixed = client.post("/estimate/year", json={"estimate": est, "year": 1851})
    assert fixed.status_code == 200, fixed.text
    fixed = fixed.json()
    assert fixed["identification"]["year"] == 1851
    assert fixed["identification"]["title"] == "10 Francs Cérès 1851 A"
    assert fixed["valuation"]["retail_low"] == 600
    assert fixed["photos"] == est["photos"]
    assert fixed["year_check"] is None

    # a year the user confirms is not asked again, even without a listing
    kept = client.post("/estimate/year", json={"estimate": est, "year": 1861}).json()
    assert kept["valuation"] is None and kept["year_check"] is None


def test_year_correction_rejects_garbage():
    assert client.post("/estimate/year", json={"estimate": {}, "year": 1851}).status_code == 422


def test_collection_total_counts_unpriced_coins_at_their_metal_value(monkeypatch, catalog_1851):
    monkeypatch.setattr(identify, "identify", lambda images, language: make_coin())
    priced = client.post("/estimate", files={"front": ("f.jpg", jpeg(), "image/jpeg")})
    monkeypatch.setattr(identify, "identify", lambda images, language: make_coin(year=1861))
    unpriced = client.post("/estimate", files={"front": ("f.jpg", jpeg(), "image/jpeg")}).json()
    ids = [
        client.post("/collection", json={"estimate": priced.json()}).json()["id"],
        client.post("/collection", json={"estimate": unpriced, "quantity": 2}).json()["id"],
    ]
    t = client.get("/collection", params={"currency": "EUR"}).json()["totals"]
    melt = unpriced["melt"]["value"]
    assert (t["count"], t["priced_count"], t["unpriced_count"]) == (3, 1, 2)
    assert t["value_low"] == 480
    assert t["unpriced_melt"] == round(2 * melt, 2)
    assert t["total_low"] == round(480 + 2 * melt, 2)
    for i in ids:
        client.delete(f"/collection/{i}")


def test_photo_thumbnail(monkeypatch, fake_vision):
    buf = io.BytesIO()
    Image.new("RGB", (1200, 900), "gold").save(buf, "JPEG")
    est = client.post("/estimate", files={"front": ("f.jpg", buf.getvalue(), "image/jpeg")}).json()
    name = est["photos"]["front"]
    full = Image.open(io.BytesIO(client.get(f"/uploads/{name}").content))
    thumb = Image.open(io.BytesIO(client.get(f"/uploads/{name}?size=thumb").content))
    assert full.size == (1200, 900)
    assert max(thumb.size) == main.THUMB_SIDE


def test_photo_without_thumbnail_gets_one(monkeypatch, fake_vision):
    buf = io.BytesIO()
    Image.new("RGB", (1000, 1000), "gold").save(buf, "JPEG")
    main.store.put_photo("old.jpg", buf.getvalue())  # stored before thumbnails existed
    thumb = Image.open(io.BytesIO(client.get("/uploads/old.jpg?size=thumb").content))
    assert thumb.size == (main.THUMB_SIDE, main.THUMB_SIDE)
    assert main.store.thumb("old.jpg")[0] is not None  # kept for next time


def test_reprice_a_saved_coin_with_its_corrected_year_and_grade(monkeypatch, catalog_1851):
    monkeypatch.setattr(identify, "identify", lambda images, language: make_coin(year=1850))  # misread, no listing
    est = client.post("/estimate", files={"front": ("f.jpg", jpeg(), "image/jpeg")}).json()
    item = client.post("/collection", json={"estimate": est}).json()
    assert item["value_low"] is None
    client.patch(f"/collection/{item['id']}", json={"year": 1851, "grade": "SUP"})  # the user corrects the coin

    preview = client.post(f"/collection/{item['id']}/reprice", params={"save": "false"}).json()
    assert preview["estimate"]["valuation"]["retail_low"] > 600  # SUP, between TTB 600 and SUP 1000
    assert client.get(f"/collection/{item['id']}").json()["value_low"] is None  # preview changes nothing

    saved = client.post(f"/collection/{item['id']}/reprice").json()
    assert saved["value_low"] == preview["estimate"]["valuation"]["value_low"]
    assert (saved["year"], saved["grade"]) == (1851, "SUP")
    assert saved["estimate"]["identification"]["year"] == 1851
    client.delete(f"/collection/{item['id']}")
