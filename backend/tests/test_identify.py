import pytest

from app import identify
from tests.test_api import client, jpeg
from tests.test_catalog import make_coin


@pytest.fixture
def gateway(monkeypatch):
    """Capture the request body; answer with `reply` (a message content string)."""
    state = {"reply": make_coin(confidence=0.99).model_dump_json()}  # sure: no second look

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


@pytest.mark.parametrize(
    "first, second_look",
    [
        (dict(status="identified", confidence=0.99), False),
        (dict(status="identified", confidence=0.85), True),  # sure enough to name it, not to be trusted
        (dict(status="unidentifiable", confidence=0.4), True),
        (dict(status="not_a_coin", confidence=0.0), False),  # a glass stays a glass
    ],
)
def test_unsure_readings_get_a_second_look(gateway, monkeypatch, first, second_look):
    models = []

    def fake_request(body):
        models.append(body["model"])
        coin = make_coin(**first) if len(models) == 1 else make_coin(title="1 Centime Cérès", confidence=0.95)
        return {"model": body["model"], "choices": [{"message": {"content": coin.model_dump_json()}}]}

    monkeypatch.setattr(identify, "_request", fake_request)
    coin = identify.identify([(b"x", "image/jpeg")])
    assert models == [identify.MODEL, identify.ESCALATION_MODELS[0]][: 1 + second_look]
    assert (coin.title == "1 Centime Cérès") is second_look  # the stronger model's reading is kept


def test_a_failed_second_look_tries_the_next_model_then_keeps_the_first_reading(monkeypatch):
    calls = []

    def fake_request(body):
        calls.append(body["model"])
        if len(calls) > 1:
            raise identify.VisionError("no usable answer")
        return {
            "model": body["model"],
            "choices": [{"message": {"content": make_coin(confidence=0.8).model_dump_json()}}],
        }

    monkeypatch.setattr(identify, "_request", fake_request)
    assert identify.identify([(b"x", "image/jpeg")]).confidence == 0.8
    assert calls == [identify.MODEL, *identify.ESCALATION_MODELS]


def test_second_look_can_be_turned_off(gateway, monkeypatch):
    monkeypatch.setattr(identify, "ESCALATION_MODELS", [])
    assert not identify.needs_second_look(make_coin(status="unidentifiable", confidence=0.1))
