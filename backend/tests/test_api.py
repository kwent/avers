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
def fake_claude(monkeypatch):
    calls = {}

    def fake_identify(images, language):
        calls["language"] = language
        return make_coin()

    monkeypatch.setattr(identify, "identify", fake_identify)
    monkeypatch.setattr(
        identify,
        "valuate",
        lambda coin, melt, comps, cur, language: identify.Valuation(
            value_low=400, value_high=600, retail_low=700, retail_high=900, best_match_ids=[], explanation="test"
        ),
    )
    return calls


def test_health():
    assert client.get("/health").json()["ok"] is True


def test_estimate_then_collection_roundtrip(fake_claude):
    res = client.post(
        "/estimate",
        files={"front": ("f.jpg", jpeg(), "image/jpeg"), "back": ("b.jpg", jpeg(), "image/jpeg")},
        data={"currency": "EUR"},
    )
    assert res.status_code == 200, res.text
    est = res.json()
    assert est["identification"]["year"] == 1851
    assert est["melt"]["metal"] == "gold"
    assert est["valuation"]["value_low"] == 400
    assert est["already_owned"] == 0

    # uploaded photo is downsized and served back
    photo = client.get(f"/uploads/{est['photos']['front']}")
    assert photo.status_code == 200
    assert max(Image.open(io.BytesIO(photo.content)).size) <= main.MAX_SIDE

    item = client.post("/collection", json={"estimate": est, "quantity": 2}).json()
    client.patch(f"/collection/{item['id']}", json={"quantity": 3, "notes": "héritage"})

    col = client.get("/collection", params={"currency": "EUR"}).json()
    assert col["totals"]["count"] == 3
    assert col["totals"]["value_low"] == 1200
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
    assert client.get("/health").status_code == 401
    assert client.get("/health", headers={"X-App-Token": "secret"}).status_code == 200


@pytest.mark.parametrize("sent,used", [("en", "en"), ("fr", "fr"), ("xx", "fr")])
def test_estimate_language(fake_claude, sent, used):
    res = client.post("/estimate", files={"front": ("f.jpg", jpeg(), "image/jpeg")}, data={"language": sent})
    assert res.json()["language"] == used
    assert fake_claude["language"] == used


def test_prompts_name_the_language():
    assert "in English" in identify.IDENTIFY_PROMPT.format(language=identify.language_name("en"))
    assert identify.language_name("de") == "French"  # unsupported -> default
