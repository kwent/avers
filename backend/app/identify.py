"""The vision-model reading of an estimate: read the coin from the photos (or refuse: not a coin / unidentifiable).

Goes through the Vercel AI Gateway (OpenAI-compatible API), so the model is a setting, not code. The default was
picked with bench/models.py: Gemini Flash-Lite reads clean coins as well as the large models here, at a fraction of
the cost and latency; the gateway falls back to the next model if it fails. Worn or glary real-life coins are where
it slips (a 1 centime Cérès read as Napoléon III, 3 times out of 3, at 0.85-0.9): a reading it is not sure of gets
a second look by a stronger model, whose reading is kept.
"""

import base64
import html
import json
import logging
import os
import urllib.error
import urllib.request
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.http import SSL_CTX

GATEWAY_URL = os.environ.get("AI_GATEWAY_URL", "https://ai-gateway.vercel.sh/v1")
MODEL = os.environ.get("VISION_MODEL", "google/gemini-3.5-flash-lite")
FALLBACK_MODELS = [m for m in os.environ.get("VISION_FALLBACK_MODELS", "google/gemini-3.8-flash").split(",") if m]
# Second look when the first reading is unidentifiable or below ESCALATE_BELOW: the first of these models that
# gives a usable answer (empty: off). Gemini 3.8 Flash, then Opus if it fails: both read the worn 1 centime Cérès
# right 3 times out of 3 where Flash-Lite said Napoléon III.
ESCALATION_MODELS = [
    m
    for m in os.environ.get("VISION_ESCALATION_MODELS", "google/gemini-3.8-flash,anthropic/claude-opus-5.5").split(",")
    if m
]
ESCALATE_BELOW = float(os.environ.get("VISION_ESCALATE_BELOW", "0.95"))
TIMEOUT = 90

log = logging.getLogger(__name__)

Metal = Literal[
    "gold",
    "silver",
    "platinum",
    "palladium",
    "billon",
    "copper",
    "bronze",
    "nickel",
    "aluminium",
    "steel",
    "zinc",
    "other",
    "unknown",
]
Grade = Literal["B", "TB", "TTB", "SUP", "SPL", "FDC", "unknown"]
Status = Literal["identified", "not_a_coin", "unidentifiable"]
Side = Literal["obverse", "reverse", "unclear"]

# Below this self-reported confidence an identification is treated as unidentifiable.
MIN_CONFIDENCE = 0.5


class VisionError(RuntimeError):
    """The vision model could not be reached or gave no usable answer."""

    def __init__(self, message: str, status: int | None = None, retry_after: float | None = None):
        super().__init__(message)
        self.status = status  # HTTP status from the gateway, if any
        self.retry_after = retry_after


class CoinIdentification(BaseModel):
    status: Status = Field(
        description="identified: you know which coin this is; not_a_coin: no coin in the photos "
        "(any other object, banknote, token, jewellery...); unidentifiable: a coin, but not readable or "
        "recognisable enough to name it with confidence"
    )
    status_reason: str | None = Field(
        description="When status is not 'identified': one short sentence saying what you see and why you cannot "
        "identify it (e.g. 'This is a drinking glass, not a coin.', 'The legend and date are not legible.')"
    )
    photo_sides: list[Side] = Field(description="For each photo, in order: which side of the coin it shows")
    title: str = Field(description="Short display name, e.g. '10 Francs Cérès 1851 A'; empty if not identified")
    country_iso: str | None = Field(description="ISO 3166-1 alpha-2 of the issuing country, e.g. FR, IT, CH")
    country_name: str | None = Field(description="Country name")
    year: int | None
    mint_mark: str | None = Field(description="Mint mark letter/symbol, e.g. 'A' (Paris)")
    face_value: float | None = Field(description="Numeric face value, e.g. 10 for 10 Francs")
    denomination: str | None = Field(description="Face value with unit, e.g. '10 Francs'")
    type_name: str | None = Field(description="Type/series, e.g. 'Cérès, IIe République'")
    metal: Metal
    fineness: float | None = Field(description="Precious metal purity as a fraction, e.g. 0.900")
    weight_g: float | None = Field(description="Standard weight in grams for this type")
    catalog_refs: list[str] = Field(
        description="Known references, e.g. ['G. 1012', 'KM 770']; Gadoury refs as 'G. <n>'"
    )
    grade: Grade = Field(description="Estimated condition on the French scale (codes kept as-is in every language)")
    grade_notes: str = Field(description="One sentence explaining the grade")
    confidence: float = Field(description="0-1 confidence in the identification")
    authenticity_notes: str | None = Field(description="Note if it may be a copy/replica/fantasy, else null")
    notes: str = Field(description="Short notes useful to a collector (variety, rarity)")


# UI languages supported by the app -> language name used in prompts
LANGUAGES = {"fr": "French", "en": "English"}
DEFAULT_LANGUAGE = "fr"

IDENTIFY_PROMPT = """You are an expert numismatist helping a collector identify a coin from photos.

First decide what the photos show, and never guess:
- If they do not show a coin (a glass, a banknote, a medal, a token, a person, a blank image...), set status
  "not_a_coin", say what you see in status_reason, and leave every coin field empty/null/unknown.
- If they show a coin but you cannot read or recognise enough of it (blur, glare, wear, cropping, unknown type)
  to name it with real confidence, set status "unidentifiable", say what is missing in status_reason, and leave
  the coin fields you cannot actually see empty/null/unknown. Do not fill gaps with likely-looking values.
- Only set status "identified" when the country, denomination and type are actually visible or certain.

When identified, give country, year, mint mark, denomination, type, metal, standard weight and fineness, and
catalog references (Gadoury 'G. <n>' for French coins when known, KM). Estimate the grade on the French scale
(B, TB, TTB, SUP, SPL, FDC) from visible wear and surface. A field you cannot read stays null even when the rest
is identified (e.g. a worn date). confidence is your honest probability that the identification is right.

The photos are meant to be the obverse then the reverse, but the user may have swapped them or shot the same
side twice: report what each photo really shows in photo_sides.
Write every free-text field (title, country_name, denomination, type_name, notes, status_reason) in {language}."""


def _strict(schema: dict) -> dict:
    """Strict JSON schema (every property required, no extras), as structured outputs expect."""
    if isinstance(schema, dict):
        if schema.get("type") == "object" and "properties" in schema:
            schema["additionalProperties"] = False
            schema["required"] = list(schema["properties"])
        for v in schema.values():
            _strict(v)
    elif isinstance(schema, list):
        for v in schema:
            _strict(v)
    return schema


SCHEMA = _strict(CoinIdentification.model_json_schema())


def language_name(code: str) -> str:
    return LANGUAGES.get(code, LANGUAGES[DEFAULT_LANGUAGE])


def _request(body: dict) -> dict:
    key = os.environ.get("AI_GATEWAY_API_KEY")
    if not key:
        raise VisionError("AI_GATEWAY_API_KEY is not set")
    req = urllib.request.Request(
        f"{GATEWAY_URL}/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=SSL_CTX) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        retry_after = e.headers.get("Retry-After") if e.headers else None
        raise VisionError(
            f"vision model error {e.code}: {e.read().decode(errors='replace')[:300]}",
            status=e.code,
            retry_after=float(retry_after) if retry_after and retry_after.isdigit() else None,
        ) from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise VisionError(f"vision model unreachable: {e}") from e


def read(
    images: list[tuple[bytes, str]], language: str = DEFAULT_LANGUAGE, model: str | None = None
) -> tuple[CoinIdentification, dict]:
    """images: [(bytes, media_type)] — front first, then back. Returns the reading and the raw response."""
    content = []
    labels = ["Photo 1 (meant to be the obverse)", "Photo 2 (meant to be the reverse)"]
    for label, (data, media_type) in zip(labels[: len(images)], images, strict=True):
        url = f"data:{media_type};base64,{base64.standard_b64encode(data).decode()}"
        content += [{"type": "text", "text": label}, {"type": "image_url", "image_url": {"url": url}}]
    content.append({"type": "text", "text": "What is this? Identify the coin only if you really can."})
    body = {
        "model": model or MODEL,
        "messages": [
            {"role": "system", "content": IDENTIFY_PROMPT.format(language=language_name(language))},
            {"role": "user", "content": content},
        ],
        "response_format": {"type": "json_schema", "json_schema": {"name": "coin", "schema": SCHEMA, "strict": True}},
        "max_tokens": 8000,
    }
    if model is None and FALLBACK_MODELS:
        body["providerOptions"] = {"gateway": {"models": FALLBACK_MODELS}}
    resp = _request(body)
    try:
        text = (resp["choices"][0]["message"]["content"] or "").strip()
        if text.startswith("```"):  # some models wrap JSON in a code fence despite structured outputs
            text = text.strip("`").removeprefix("json")
        coin = _unescape(CoinIdentification.model_validate_json(text))
    except (KeyError, IndexError, ValidationError) as e:
        raise VisionError(f"no usable answer from {resp.get('model', body['model'])}") from e
    return enforce_confidence(coin), resp


def _unescape(coin: CoinIdentification) -> CoinIdentification:
    """Some models HTML-escape accents in JSON strings ('C&#233;r&#232;s')."""
    for name, value in coin:
        if isinstance(value, str):
            setattr(coin, name, html.unescape(value))
        elif isinstance(value, list):
            setattr(coin, name, [html.unescape(v) if isinstance(v, str) else v for v in value])
    return coin


def identify(images: list[tuple[bytes, str]], language: str = DEFAULT_LANGUAGE) -> CoinIdentification:
    coin = read(images, language)[0]
    if not needs_second_look(coin):
        return coin
    for model in ESCALATION_MODELS:
        try:
            second = read(images, language, model=model)[0]
        except VisionError as e:
            log.warning("second look by %s failed: %s", model, e)
            continue
        log.warning("second look by %s: %s %.2f -> %s %.2f", model, coin.status, coin.confidence,
                    second.status, second.confidence)  # fmt: skip
        return second
    return coin  # no second look came through: the first reading stands


def needs_second_look(coin: CoinIdentification) -> bool:
    """A coin the first model could not name, or named without being sure. Not "not a coin": that is not a
    matter of reading skill."""
    if not ESCALATION_MODELS or coin.status == "not_a_coin":
        return False
    return coin.status == "unidentifiable" or coin.confidence < ESCALATE_BELOW


def enforce_confidence(coin: CoinIdentification) -> CoinIdentification:
    """Server-side backstop for 'never guess': a low-confidence identification is not an identification."""
    if coin.status == "identified" and coin.confidence < MIN_CONFIDENCE:
        coin.status = "unidentifiable"
        coin.status_reason = coin.status_reason or None  # the app shows its own wording when empty
    return coin
