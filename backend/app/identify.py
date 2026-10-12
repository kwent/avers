"""Claude calls: identify a coin from photos, then value it against catalog comparables."""

import base64
import json
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"

client = anthropic.Anthropic()

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


class CoinIdentification(BaseModel):
    is_coin: bool = Field(description="False if the photo does not show a coin")
    title: str = Field(description="Short display name, e.g. '10 Francs Cérès 1851 A'")
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


class Valuation(BaseModel):
    value_low: float = Field(description="Low estimate of what a collector could realistically get")
    value_high: float
    retail_low: float | None = Field(description="Typical dealer asking price, low")
    retail_high: float | None
    best_match_ids: list[int] = Field(description="Catalog ids of the comparables that are the same coin type")
    explanation: str = Field(description="2-4 short sentences explaining the estimate")


# UI languages supported by the app -> language name used in prompts
LANGUAGES = {"fr": "French", "en": "English"}
DEFAULT_LANGUAGE = "fr"

IDENTIFY_PROMPT = """You are an expert numismatist helping a collector identify a coin from photos.
Identify the coin as precisely as the photos allow: country, year, mint mark, denomination, type, metal,
standard weight and fineness, and catalog references (Gadoury 'G. <n>' for French coins when known, KM).
Estimate the grade on the French scale (B, TB, TTB, SUP, SPL, FDC) from visible wear and surface.
If something is not readable, say so in notes and lower confidence rather than guessing.
Write every free-text field (title, country_name, denomination, type_name, notes) in {language}."""

VALUATION_PROMPT = """You are an expert numismatist. Estimate the value of this coin for a private collector.

Coin identified from photos:
{coin}

Melt value of the metal content right now: {melt}

Comparable listings from dealer catalogs (asking prices, {currency};
in_stock=0 means an archived past listing, often dated):
{comparables}

Rules:
- Dealer asking prices are retail; what a private collector can sell for is usually lower.
- Weigh comparables of the same type, year and grade most; adjust for grade differences.
- Never estimate below melt value.
- Values in {currency}.
- Write the explanation in {language}."""


def _image_block(data: bytes, media_type: str) -> dict:
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": base64.standard_b64encode(data).decode()},
    }


def _parse(**kwargs):
    response = client.beta.messages.parse(
        model=MODEL,
        max_tokens=16000,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        **kwargs,
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to analyse this image")
    if response.parsed_output is None:
        raise RuntimeError(f"No structured output (stop_reason={response.stop_reason})")
    return response.parsed_output


def language_name(code: str) -> str:
    return LANGUAGES.get(code, LANGUAGES[DEFAULT_LANGUAGE])


def identify(images: list[tuple[bytes, str]], language: str = DEFAULT_LANGUAGE) -> CoinIdentification:
    """images: [(bytes, media_type)] — front first, then back."""
    content = []
    for label, (data, media_type) in zip(["Obverse (front)", "Reverse (back)"][: len(images)], images, strict=True):
        content += [{"type": "text", "text": label}, _image_block(data, media_type)]
    content.append({"type": "text", "text": "Identify this coin."})
    return _parse(
        system=IDENTIFY_PROMPT.format(language=language_name(language)),
        output_config={"effort": "medium"},
        messages=[{"role": "user", "content": content}],
        output_format=CoinIdentification,
    )


def valuate(
    coin: CoinIdentification,
    melt: dict | None,
    comparables: list[dict],
    currency: str,
    language: str = DEFAULT_LANGUAGE,
) -> Valuation:
    prompt = VALUATION_PROMPT.format(
        coin=coin.model_dump_json(indent=1),
        melt=json.dumps(melt) if melt else "n/a (non-precious metal or unknown weight)",
        comparables=json.dumps(comparables, ensure_ascii=False, indent=1) if comparables else "none found",
        currency=currency,
        language=language_name(language),
    )
    return _parse(
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": prompt}],
        output_format=Valuation,
    )
