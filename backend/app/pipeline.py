"""The /estimate pipeline: one vision-model call to read the photos; the catalog is the source of truth for the rest.

1. A vision model reads the photos (identify) — the only AI call.
2. Plain rules + local visual similarity find the catalog entry (app.matching); its facts override the reading.
3. Prices come from the catalog listings of that coin, computed in app.pricing.
"""

import logging
import re
import sqlite3
import time

from app import catalog, collection, identify, matching, metals, pricing

log = logging.getLogger(__name__)

# catalog metal wording -> normalized metal
CATALOG_METAL = {"Or": "gold", "Argent": "silver", "Billon": "billon", "Platine": "platinum"}


def _year(value: str | None) -> int | None:
    m = re.match(r"(\d{4})", value or "")
    return int(m.group(1)) if m else None


def _apply_catalog_facts(coin: identify.CoinIdentification, row: sqlite3.Row) -> None:
    """The matched catalog entry is the reference for the facts it records."""
    if row["weight_g"]:
        coin.weight_g = row["weight_g"]
    if CATALOG_METAL.get(row["metal"] or ""):
        coin.metal = CATALOG_METAL[row["metal"]]
    listed = matching.listing_refs(row["name"])
    if listed:  # the listing's Gadoury numbers replace whatever the reading claimed
        others = [r for r in coin.catalog_refs if not matching.gadoury_refs([r])]
        coin.catalog_refs = [f"G. {ref}" for ref in sorted(listed)] + others


def run(
    photos: list[tuple[bytes, str]],
    currency: str,
    language: str,
    catalog_db: sqlite3.Connection,
    collection_db: sqlite3.Connection,
    index=None,
) -> dict:
    """photos: [(jpeg bytes, stored file name)], front first."""
    t0 = time.monotonic()
    coin = identify.identify([(data, "image/jpeg") for data, _ in photos], language)
    log.warning("estimate identified (%s, %.2f) +%.1fs", coin.status, coin.confidence, time.monotonic() - t0)

    names = [name for _, name in photos]
    photo_warning = None
    if len(names) == 2 and len(coin.photo_sides) == 2:
        if coin.photo_sides == ["reverse", "obverse"]:
            names.reverse()  # the user swapped the sides: show the obverse first
        elif coin.photo_sides[0] == coin.photo_sides[1] != "unclear":
            photo_warning = "same_side"

    result = {
        "currency": currency,
        "language": language,
        "photos": {"front": names[0], "back": names[1] if len(names) > 1 else None},
        "photo_warning": photo_warning,
        "identification": coin.model_dump(),
        "match": None,
        "melt": None,
        "comparables": [],
        "price_table": [],
        "valuation": None,
    }
    if coin.status != "identified":
        return result  # never value something we could not identify

    match = matching.find(catalog_db, coin, [data for data, _ in photos], index)
    log.warning("estimate matched (%s) +%.1fs", match and match.row["id"], time.monotonic() - t0)
    if match:
        _apply_catalog_facts(coin, match.row)
        images = catalog_db.execute(
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
    result["already_owned"] = collection.owned_count(collection_db, coin.country_iso, coin.year, coin.denomination)
    melt = metals.melt_value(coin.metal, coin.weight_g, coin.fineness, currency)
    result["melt"] = melt

    same = match.same if match else []
    same_ids = {r["id"] for r in same}
    comparables = catalog.comparables(catalog_db, coin, currency)
    result["comparables"] = sorted(comparables, key=lambda c: c["id"] not in same_ids)
    if not same:
        return result  # no catalog listing of this exact coin: no price rather than a made-up one

    points = []
    for r in same:
        price = metals.convert(r["price"], r["currency"], currency)
        if price:
            points.append(
                pricing.Point(
                    source=r["source"],
                    price=price,
                    grade=r["grade"],
                    rank=pricing.grade_rank(r["grade"]),
                    year=_year(r["modified"] or r["created"]),
                    kind="listing" if r["in_stock"] else "sold",
                    url=r["url"],
                )
            )
    melt_now = melt["value"] if melt else None
    pricing.prepare(
        points,
        melt["metal"] if melt else None,
        melt["pure_metal_g"] if melt else None,
        melt_now,
        metals.convert(1, "USD", currency),
    )
    table = pricing.price_table(points, melt_now)
    result["price_table"] = [pricing.to_dict(r) for r in table]
    est = pricing.estimate(table, coin.grade, melt_now)
    if est is not None:
        years = [p.year for p in points if p.year]
        result["valuation"] = {
            "value_low": est.value_low,
            "value_high": est.value_high,
            "retail_low": est.retail_low,
            "retail_high": est.retail_high,
            "best_match_ids": sorted(same_ids),
            # facts for the app's own wording (no generated text)
            "basis": {
                "listings": len(points),
                "first_year": min(years) if years else None,
                "last_year": max(years) if years else None,
                "metal_share": round(melt_now / est.retail_high, 2) if melt_now and est.retail_high else None,
            },
        }
    return result
