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
Status = Literal["identified", "not_a_coin", "unidentifiable"]
Side = Literal["obverse", "reverse", "unclear"]

# Below this self-reported confidence an identification is treated as unidentifiable.
MIN_CONFIDENCE = 0.5


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


class CatalogMatch(BaseModel):
    match_id: int | None = Field(
        description="Catalog id of the candidate that is the same coin (same country, type, denomination, year and "
        "mint; grade may differ), or null if none is"
    )
    same_coin_ids: list[int] = Field(description="Every candidate id that is that same coin, in any grade")
    confidence: float = Field(description="0-1 probability that match_id is right")
    reason: str = Field(description="One short sentence: what confirms or rules out the match")


GradeCode = Literal["B", "TB", "TTB", "SUP", "SPL", "FDC"]


class MarketQuote(BaseModel):
    source: str = Field(description="Site or auction house, e.g. 'CGB', 'Heritage', 'eBay'")
    url: str
    grade: GradeCode | None = Field(description="Grade converted to the French scale, null if not stated")
    grade_text: str | None = Field(description="Grade as written by the source, e.g. 'NGC MS64', 'TTB+'")
    price: float
    currency: str = Field(description="ISO 4217 code, e.g. EUR, USD")
    year: int | None = Field(description="Year of the sale or listing, null if unknown")
    kind: Literal["sold", "listing"] = Field(description="sold = auction result / completed sale; listing = asking")


class MarketQuotes(BaseModel):
    quotes: list[MarketQuote]


class Explanation(BaseModel):
    explanation: str = Field(description="2-4 short sentences")


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

MATCH_PROMPT = """You are an expert numismatist. The user's photos of a coin come first, then numbered candidate
coins from a dealer catalog (each candidate image shows its obverse and reverse side by side).

Find the candidate that is the same coin: same country, type, denomination, year and mint mark. The grade (state of
wear) may differ. Compare the actual designs, legends, dates and mint marks; do not match on a similar look alone.
If none is the same coin, match_id is null — that is a valid, useful answer. Never pick the closest one by default.
Your own first reading of the coin (may be wrong): {reading}
Write the reason in {language}."""

QUOTES_PROMPT = """Find recent market prices for this exact coin: {coin}.
Search auction results and dealer listings (e.g. CGB, iNumis, NumisCorner, Heritage, eBay sold listings,
Numista price pages). Report only prices you actually found on a page, with the page URL, the grade as written
and converted to the French scale (B, TB, TTB, SUP, SPL, FDC; US: G/VG≈B, F≈TB, VF≈TTB, XF/EF≈SUP, AU≈SPL,
MS/UNC≈FDC), the year of the sale or listing, and whether it is a completed sale or an asking price.
Skip lots of several coins, different years or mints, and certified-grade premiums you cannot attribute.
Return between 0 and 8 quotes; an empty list is better than a doubtful one."""

EXPLAIN_PROMPT = """Explain this coin estimate to a collector in {language}, in 2-4 short sentences: what drives
the value (metal content vs collector premium), how the grade changes the price, and where the numbers come from
(catalog listings, recent market quotes). Do not invent figures: only use the ones below.

Coin: {coin}
Estimated grade: {grade}
Melt value now: {melt}
Price by grade (retail / private resale, {currency}): {table}
Estimate for this grade: {estimate}
Data used (price points; 'undated' means the date is unknown — never call those recent): {sources}"""


def _image_block(data: bytes, media_type: str) -> dict:
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": base64.standard_b64encode(data).decode()},
    }


def _parse(messages: list, max_continuations: int = 3, **kwargs):
    response = None
    for _ in range(max_continuations + 1):
        response = client.beta.messages.parse(
            model=MODEL,
            max_tokens=16000,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            messages=messages,
            **kwargs,
        )
        if response.stop_reason != "pause_turn":
            break
        # server-side tool loop (web search) paused: resend the turn as-is and the server resumes it
        messages = [*messages, {"role": "assistant", "content": response.content}]
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
    labels = ["Photo 1 (meant to be the obverse)", "Photo 2 (meant to be the reverse)"]
    for label, (data, media_type) in zip(labels[: len(images)], images, strict=True):
        content += [{"type": "text", "text": label}, _image_block(data, media_type)]
    content.append({"type": "text", "text": "What is this? Identify the coin only if you really can."})
    coin = _parse(
        system=IDENTIFY_PROMPT.format(language=language_name(language)),
        output_config={"effort": "medium"},
        messages=[{"role": "user", "content": content}],
        output_format=CoinIdentification,
    )
    return enforce_confidence(coin)


def enforce_confidence(coin: CoinIdentification) -> CoinIdentification:
    """Server-side backstop for 'never guess': a low-confidence identification is not an identification."""
    if coin.status == "identified" and coin.confidence < MIN_CONFIDENCE:
        coin.status = "unidentifiable"
        coin.status_reason = coin.status_reason or None  # the app shows its own wording when empty
    return coin


def match(
    photos: list[tuple[bytes, str]],
    candidates: list[dict],
    coin: CoinIdentification,
    language: str = DEFAULT_LANGUAGE,
) -> CatalogMatch:
    """candidates: [{"id", "label", "image": jpeg bytes}] — picks the catalog entry that is this coin, if any."""
    content = []
    for i, (data, media_type) in enumerate(photos, 1):
        content += [{"type": "text", "text": f"User photo {i}"}, _image_block(data, media_type)]
    for c in candidates:
        content.append({"type": "text", "text": f"Candidate #{c['id']}: {c['label']}"})
        if c.get("image"):
            content.append(_image_block(c["image"], "image/jpeg"))
    content.append({"type": "text", "text": "Which candidate, if any, is this exact coin?"})
    reading = coin.model_dump_json(include={"title", "country_iso", "year", "mint_mark", "denomination", "type_name"})
    result = _parse(
        system=MATCH_PROMPT.format(reading=reading, language=language_name(language)),
        output_config={"effort": "medium"},
        messages=[{"role": "user", "content": content}],
        output_format=CatalogMatch,
    )
    ids = {c["id"] for c in candidates}
    if result.match_id not in ids:
        result.match_id = None
    result.same_coin_ids = [i for i in result.same_coin_ids if i in ids]
    if result.match_id is not None and result.match_id not in result.same_coin_ids:
        result.same_coin_ids.insert(0, result.match_id)
    return result


def market_quotes(description: str) -> list[MarketQuote]:
    """Live web search for recent auction results / dealer prices of this exact coin."""
    return _parse(
        output_config={"effort": "low"},
        tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 4}],
        messages=[{"role": "user", "content": QUOTES_PROMPT.format(coin=description)}],
        output_format=MarketQuotes,
    ).quotes


def explain(context: dict, language: str = DEFAULT_LANGUAGE) -> str:
    prompt = EXPLAIN_PROMPT.format(
        language=language_name(language), **{k: json.dumps(v, ensure_ascii=False) for k, v in context.items()}
    )
    return _parse(
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": prompt}],
        output_format=Explanation,
    ).explanation
