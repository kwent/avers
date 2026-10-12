import pytest

from app import identify
from tests.test_api import client, jpeg
from tests.test_catalog import make_coin


@pytest.fixture
def gateway(monkeypatch):
    """Capture the request body; answer with `reply` (a message content string)."""
    state = {"reply": make_coin().model_dump_json()}

    def fake_request(body):
        state["body"] = body
        return {"model": body["model"], "choices": [{"message": {"content": state["reply"]}}]}

    monkeypatch.setattr(identify, "_request", fake_request)
    return state


def test_read_sends_photos_schema_and_fallbacks(gateway):
    coin = identify.identify([(b"front", "image/jpeg"), (b"back", "image/jpeg")], "en")
    assert coin.year == 1851
    body = gateway["body"]
    assert body["model"] == identify.MODEL
    assert body["providerOptions"]["gateway"]["models"] == identify.FALLBACK_MODELS
    assert body["response_format"]["json_schema"]["strict"] is True
    assert "in English" in body["messages"][0]["content"]
    images = [c for c in body["messages"][1]["content"] if c["type"] == "image_url"]
    assert [i["image_url"]["url"][:23] for i in images] == ["data:image/jpeg;base64,"] * 2


def test_explicit_model_has_no_fallback(gateway):
    identify.read([(b"x", "image/jpeg")], model="some/model")
    assert gateway["body"]["model"] == "some/model" and "providerOptions" not in gateway["body"]


def test_code_fenced_json_is_accepted(gateway):
    gateway["reply"] = f"```json\n{make_coin().model_dump_json()}\n```"
    assert identify.identify([(b"x", "image/jpeg")]).status == "identified"


def test_unusable_answer_is_an_error(gateway):
    gateway["reply"] = "Sorry, I can't help with that."
    with pytest.raises(identify.VisionError):
        identify.identify([(b"x", "image/jpeg")])


def test_low_confidence_reading_is_downgraded(gateway):
    gateway["reply"] = make_coin(confidence=0.2).model_dump_json()
    assert identify.identify([(b"x", "image/jpeg")]).status == "unidentifiable"


def test_missing_key_is_an_error(monkeypatch):
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    with pytest.raises(identify.VisionError, match="AI_GATEWAY_API_KEY"):
        identify._request({})


def test_estimate_reports_vision_failure_as_502(monkeypatch):
    def fail(images, language):
        raise identify.VisionError("vision model error 429: busy", status=429)

    monkeypatch.setattr(identify, "identify", fail)
    res = client.post("/estimate", files={"front": ("f.jpg", jpeg(), "image/jpeg")})
    assert res.status_code == 502 and "429" in res.json()["detail"]


def test_html_entities_are_decoded(gateway):
    gateway["reply"] = make_coin(title="10 Francs C&#233;r&#232;s", catalog_refs=["G.&#160;1012"]).model_dump_json()
    coin = identify.identify([(b"x", "image/jpeg")])
    assert coin.title == "10 Francs Cérès" and coin.catalog_refs == ["G.\xa01012"]
