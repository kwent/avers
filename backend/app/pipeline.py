"""The /estimate pipeline: one vision-model call to read the photos; the catalog is the source of truth for the rest.

1. A vision model reads the photos (identify) — the only AI call.
2. Plain rules + local visual similarity find the catalog entry (app.matching); its facts override the reading.
3. Prices come from the catalog listings of that coin, computed in app.pricing.

When the year read has no listing, the result carries a `year_check` so the app can ask the user which year the
coin shows; `correct_year` then re-prices the same reading with that year (no new AI call).
"""

import logging
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import date

import numpy as np

from app import catalog, collection, identify, matching, metals, numista, pricing, visual, years
from app.listing import gadoury_refs, stored_refs

log = logging.getLogger(__name__)


def _year(value: str | None) -> int | None:
    m = re.match(r"(\d{4})", value or "")
    return int(m.group(1)) if m else None


def _apply_catalog_facts(coin: identify.CoinIdentification, row: sqlite3.Row) -> None:
    """The matched catalog entry is the reference for the facts it records."""
    if row["weight_g"]:
        coin.weight_g = row["weight_g"]
    if row["metal"] in metals.METAL_OF_CATALOG:
        coin.metal = metals.METAL_OF_CATALOG[row["metal"]]
    listed = stored_refs(row["gadoury"])
    if listed:  # the listing's Gadoury numbers replace whatever the reading claimed
        others = [r for r in coin.catalog_refs if not gadoury_refs([r])]
        coin.catalog_refs = [f"G. {ref}" for ref in sorted(listed)] + others


def _listing_points(rows: list[sqlite3.Row], currency: str) -> list[pricing.Point]:
    """Catalog listings of the coin as price points (asking prices, or sold when out of stock)."""
    points = []
    for r in rows:
        listed = metals.convert(r["price"], r["currency"], currency)
        if listed:
            points.append(
                pricing.Point(
                    source=r["source"],
                    price=listed,
                    grade=r["grade"],
                    rank=pricing.grade_rank(r["grade"]),
                    year=_year(r["modified"] or r["created"]),
                    kind="listing" if r["in_stock"] else "sold",
                    url=r["url"],
                )
            )
    return points


def _numista_points(ref: dict | None) -> list[pricing.Point]:
    """Numista's current estimate per grade (market prices), priced like listings: same grade table, melt floor
    and resale rule."""
    if not ref:
        return []
    this_year = date.today().year
    return [
        pricing.Point(
            source="numista", price=p, grade=g, rank=pricing.grade_rank(g), year=this_year, kind="sold", url=ref["url"]
        )
        for g, p in ref["prices"].items()
    ]


def set_year(coin: identify.CoinIdentification, year: int) -> None:
    if coin.year and coin.title:  # the title was written from the reading: carry the new year into it
        coin.title = coin.title.replace(str(coin.year), str(year))
    coin.year = year


@dataclass
class Sources:
    """Where an estimate looks things up: the catalog, the store (collection, photos, API cache), the visual index."""

    catalog_db: sqlite3.Connection
    store: collection.Store
    index: object = None


@dataclass
class Shots:
    """The photos of an estimate: stored names (obverse first), their visual query vectors, a warning about them."""

    names: list[str]
    queries: list[np.ndarray]
    warning: str | None = None
    swapped: bool = False  # the obverse was sent second: names are in display order, the upload order reversed


def _queries(photos: list[tuple[bytes, str]], src: Sources) -> list[np.ndarray]:
    """Visual query vectors of the photos, kept with them so a re-price (correct_year) needs no model run."""
    if src.index is None:
        return []
    out = []
    for data, name in photos:
        q = src.index.query(data)
        if isinstance(q, np.ndarray):
            src.store.set_embedding(name, q.astype(np.float32).tobytes())
        out.append(q)
    return out


def run(photos: list[tuple[bytes, str]], currency: str, language: str, src: Sources) -> dict:
    """photos: [(jpeg bytes, stored file name)], front first."""
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=1) as pool:  # the visual model runs while the vision model reads the photos
        queries = pool.submit(_queries, photos, src)
        coin = identify.identify([(data, "image/jpeg") for data, _ in photos], language)
        log.warning("estimate identified (%s, %.2f) +%.1fs", coin.status, coin.confidence, time.monotonic() - t0)
        queries = queries.result()

    names = [name for _, name in photos]
    photo_warning, swapped = None, False
    if len(names) == 2 and len(coin.photo_sides) == 2:
        if coin.photo_sides == ["reverse", "obverse"]:
            names.reverse()  # the user swapped the sides: show the obverse first
            swapped = True
        elif coin.photo_sides[0] == coin.photo_sides[1] != "unclear":
            photo_warning = "same_side"

    return price(coin, Shots(names, queries, photo_warning, swapped), currency, language, src)


def correct_year(previous: dict, year: int, src: Sources) -> dict:
    """Re-price a previous estimate with the year the user reads on the coin. Same reading, no AI call."""
    return reprice(previous, src, year=year)


def reprice(previous: dict, src: Sources, year: int | None = None, grade: str | None = None) -> dict:
    """Price a previous reading again: with the year the user reads on the coin, or a saved coin after the catalog
    or the pricing improved (with the year and grade kept in the collection, which the user may have corrected).
    Same reading, no AI call."""
    coin = identify.CoinIdentification.model_validate(previous["identification"])
    if year and year != coin.year:
        set_year(coin, year)
    if grade in pricing.GRADES:
        coin.grade = grade
    names = [n for n in (previous["photos"]["front"], previous["photos"]["back"]) if n]
    queries = []
    if src.index is not None:
        for name in names:
            vectors = src.store.embedding(name)
            if vectors is not None:
                queries.append(np.frombuffer(vectors, dtype=np.float32).reshape(-1, visual.DIM))
            elif (photo := src.store.photo(name)) is not None:  # saved before vectors were kept
                queries.append(src.index.query(photo))
    shots = Shots(names, queries, previous.get("photo_warning"), previous["photos"].get("swapped", False))
    language = previous.get("language", identify.DEFAULT_LANGUAGE)
    return price(coin, shots, previous["currency"], language, src, year_confirmed=True)


def price(
    coin: identify.CoinIdentification,
    shots: Shots,
    currency: str,
    language: str,
    src: Sources,
    year_confirmed: bool = False,
) -> dict:
    """Steps 2 and 3 for a reading: catalog match, melt value, price."""
    t0 = time.monotonic()
    result = {
        "currency": currency,
        "language": language,
        "photos": {
            "front": shots.names[0],
            "back": shots.names[1] if len(shots.names) > 1 else None,
            "swapped": shots.swapped,
        },
        "photo_warning": shots.warning,
        "identification": coin.model_dump(),
        "match": None,
        "melt": None,
        "comparables": [],
        "price_table": [],
        "valuation": None,
        "year_check": None,
        "numista": None,
    }
    if coin.status != "identified":
        return result  # never value something we could not identify

    match = matching.find(src.catalog_db, coin, shots.queries, src.index)
    log.warning("estimate matched (%s) +%.1fs", match and match.row["id"], time.monotonic() - t0)
    if match:
        _apply_catalog_facts(coin, match.row)
        images = src.catalog_db.execute(
            "SELECT url FROM coin_images WHERE coin_id = ? ORDER BY position", (match.row["id"],)
        ).fetchall()
        result["match"] = {
            "id": match.row["id"],
            "source": match.row["source"],
            "name": match.row["name"],
            "url": match.row["url"],
            "images": [r[0] for r in images],
            "confidence": match.confidence,
            "criteria": match.criteria,
            "similarity": match.similarity,
        }
    result["identification"] = coin.model_dump()
    result["already_owned"] = src.store.owned_count(coin.country_iso, coin.year, coin.denomination)
    melt = metals.melt_value(coin.metal, coin.weight_g, coin.fineness, currency)
    result["melt"] = melt

    same = match.same if match else []
    same_ids = {r["id"] for r in same}
    comparables = catalog.comparables(src.catalog_db, coin, currency)
    result["comparables"] = sorted(comparables, key=lambda c: c["id"] not in same_ids)
    points = _listing_points(same, currency)
    source = "catalog"
    if not same:  # no catalog listing of this exact coin: ask Numista, never make a price up
        lookup = coin
        if not gadoury_refs(coin.catalog_refs):  # look the type up by the catalog's Gadoury numbers
            lookup = coin.model_copy(update={"catalog_refs": matching.type_refs(src.catalog_db, coin)})
        ref = numista.lookup(src.store, lookup, currency)
        result["numista"] = ref
        result["year_check"] = years.check(src.catalog_db, coin, ref) if coin.year and not year_confirmed else None
        if result["year_check"]:
            return result  # no price until the user says which year the coin shows
        points, source = _numista_points(ref), "numista"
    if not points:
        return result

    melt_now = melt["value"] if melt else None
    pricing.prepare(
        points,
        melt["metal"] if melt else None,
        melt["pure_metal_g"] if melt else None,
        melt_now,
        metals.convert(1, "USD", currency),
    )
    table = pricing.price_table(points, melt_now)
    result["price_table"] = [asdict(r) for r in table]
    uncertain = pricing.low_confidence(points)
    est = pricing.estimate(table, coin.grade, melt_now, uncertain)
    if est is not None:
        sale_years = [p.year for p in points if p.year]
        result["valuation"] = {
            "value_low": est.value_low,
            "value_high": est.value_high,
            "retail_low": est.retail_low,
            "retail_high": est.retail_high,
            "best_match_ids": sorted(same_ids),
            "source": source,
            # facts for the app's own wording (no generated text)
            "basis": {
                "listings": len(points),
                "sold": sum(p.kind == "sold" for p in points),
                "low_confidence": uncertain,
                "first_year": min(sale_years) if sale_years else None,
                "last_year": max(sale_years) if sale_years else None,
                "metal_share": round(melt_now / est.retail_high, 2) if melt_now and est.retail_high else None,
            },
        }
    return result
