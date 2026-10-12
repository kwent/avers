"""The /estimate pipeline: the catalog is the source of truth, Claude reads photos and explains.

1. Claude reads the photos (identify) while the visual index finds look-alike catalog coins.
2. Claude picks which catalog candidate is the same coin (match), while a web search collects fresh prices.
3. The catalog entry overrides Claude's reading for the facts it holds (year, weight, references...).
4. Prices come from catalog listings + web quotes, computed in app.pricing; Claude only explains them.
"""

import io
import logging
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

from app import catalog, collection, identify, metals, pricing
from app.db import IMAGES_DIR

log = logging.getLogger(__name__)

MAX_CANDIDATES = 14
MATCH_MIN_CONFIDENCE = 0.6

# catalog metal wording -> normalized metal (first match wins)
CATALOG_METAL = {"Or": "gold", "Or nordique": "other", "Argent": "silver", "Billon": "billon", "Platine": "platinum"}


def _year(value: str | None) -> int | None:
    m = re.match(r"(\d{4})", value or "")
    return int(m.group(1)) if m else None


def _candidate_image(db: sqlite3.Connection, coin_id: int) -> bytes | None:
    """Obverse and reverse side by side, small: enough for Claude to compare designs, dates and mint marks."""
    paths = [
        r[0]
        for r in db.execute(
            "SELECT local_path FROM coin_images WHERE coin_id = ? AND local_path IS NOT NULL ORDER BY position LIMIT 2",
            (coin_id,),
        )
    ]
    tiles = []
    for p in paths:
        try:
            tiles.append(Image.open(IMAGES_DIR / p).convert("RGB").resize((320, 320)))
        except OSError:
            continue
    if not tiles:
        return None
    sheet = Image.new("RGB", (320 * len(tiles), 320), "white")
    for i, t in enumerate(tiles):
        sheet.paste(t, (320 * i, 0))
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=80)
    return buf.getvalue()


def _label(row: sqlite3.Row) -> str:
    bits = [row["name"], str(row["year"] or ""), row["grade"] or "", row["metal"] or ""]
    if row["weight_g"]:
        bits.append(f"{row['weight_g']} g")
    return " — ".join(b for b in bits if b)


def _apply_catalog_facts(coin: identify.CoinIdentification, row: sqlite3.Row) -> None:
    """The matched catalog entry is the reference for the facts it records."""
    if row["year"]:
        coin.year = row["year"]
    if row["country_iso"]:
        coin.country_iso = row["country_iso"]
    if row["face_value"]:
        coin.face_value = row["face_value"]
    if row["weight_g"]:
        coin.weight_g = row["weight_g"]
    metal = CATALOG_METAL.get(row["metal"] or "")
    if metal and metal != "other":
        coin.metal = metal
    for ref in re.findall(r"\bG\.\s*\d+[a-z]?", row["name"] or ""):
        ref = re.sub(r"\s+", " ", ref.replace("G.", "G. ")).strip()
        if not any(r.replace(" ", "") == ref.replace(" ", "") for r in coin.catalog_refs):
            coin.catalog_refs.insert(0, ref)


def _same_coin_rows(db: sqlite3.Connection, ids: list[int], match_row: sqlite3.Row | None) -> list[sqlite3.Row]:
    """Matched listings, widened to every catalog listing with the same reference, year and country."""
    rows = {r["id"]: r for r in db.execute(f"SELECT * FROM coins WHERE id IN ({','.join('?' * len(ids))})", ids)}
    if match_row is not None:
        refs = re.findall(r"\bG\.\s*(\d+[a-z]?)\b", match_row["name"] or "")
        for ref in refs:
            for r in db.execute(
                "SELECT * FROM coins WHERE country_iso = ? AND year = ? AND price > 0 AND name LIKE ?",
                (match_row["country_iso"], match_row["year"], f"%G. {ref}%"),
            ):
                rows.setdefault(r["id"], r)
    return list(rows.values())


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

    def lap(step: str) -> None:
        log.warning("estimate %s +%.1fs", step, time.monotonic() - t0)

    images = [(data, "image/jpeg") for data, _ in photos]
    with ThreadPoolExecutor(max_workers=3) as pool:
        visual_f = pool.submit(index.search, [d for d, _ in photos]) if index is not None and len(index) else None
        coin = identify.identify(images, language)
        lap(f"identified ({coin.status}, confidence {coin.confidence})")

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
            "identification": None,
            "match": None,
            "melt": None,
            "comparables": [],
            "price_table": [],
            "market_quotes": [],
            "valuation": None,
        }
        if coin.status != "identified":
            result["identification"] = coin.model_dump()
            return result  # never value something we could not identify

        # Candidates: visual look-alikes first, then the catalog search on Claude's reading.
        visual = visual_f.result() if visual_f else []
        text = [c["id"] for c in catalog.comparables(catalog_db, coin, currency, limit=MAX_CANDIDATES)]
        ids = list(dict.fromkeys([cid for cid, _ in visual] + text))[:MAX_CANDIDATES]
        rows = (
            {
                r["id"]: r
                for r in catalog_db.execute(f"SELECT * FROM coins WHERE id IN ({','.join('?' * len(ids))})", ids)
            }
            if ids
            else {}
        )
        candidates = [
            {"id": i, "label": _label(rows[i]), "image": _candidate_image(catalog_db, i)} for i in ids if i in rows
        ]

        description = " ".join(
            filter(None, [coin.title, coin.type_name, coin.country_name, " ".join(coin.catalog_refs[:2])])
        )
        quotes_f = pool.submit(identify.market_quotes, description)
        matched = identify.match(images, candidates, coin, language) if candidates else None
        lap(f"matched ({matched and matched.match_id}, {len(candidates)} candidates)")

        match_row = None
        if matched and matched.match_id is not None and matched.confidence >= MATCH_MIN_CONFIDENCE:
            match_row = rows[matched.match_id]
            _apply_catalog_facts(coin, match_row)
            img = catalog_db.execute(
                "SELECT url FROM coin_images WHERE coin_id = ? ORDER BY position", (match_row["id"],)
            ).fetchall()
            result["match"] = {
                "id": match_row["id"],
                "source": match_row["source"],
                "name": match_row["name"],
                "url": match_row["url"],
                "images": [r[0] for r in img],
                "confidence": matched.confidence,
                "reason": matched.reason,
            }
        result["identification"] = coin.model_dump()
        result["already_owned"] = collection.owned_count(collection_db, coin.country_iso, coin.year, coin.denomination)
        melt = metals.melt_value(coin.metal, coin.weight_g, coin.fineness, currency)
        result["melt"] = melt

        try:
            quotes = quotes_f.result()
            lap(f"quotes ({len(quotes)})")
        except Exception as e:  # web search is a bonus: never fail the estimate for it
            log.warning("market quotes failed: %s", e)
            quotes = []

    # Market data points: same-coin catalog listings + web quotes.
    same_ids = matched.same_coin_ids if (matched and match_row is not None) else []
    same_rows = _same_coin_rows(catalog_db, same_ids, match_row) if same_ids else []
    points: list[pricing.Point] = []
    for r in same_rows:
        price = metals.convert(r["price"], r["currency"], currency)
        if not price:
            continue
        points.append(
            pricing.Point(
                source=f"catalog:{r['source']}",
                price=price,
                grade=r["grade"],
                rank=pricing.grade_rank(r["grade"]),
                year=_year(r["modified"] or r["created"]),
                kind="listing" if r["in_stock"] else "sold",
                url=r["url"],
            )
        )
    rates = metals.usd_rates()
    for q in quotes:
        if q.currency.upper() not in rates:
            continue
        points.append(
            pricing.Point(
                source=q.source,
                price=metals.convert(q.price, q.currency.upper(), currency),
                grade=q.grade_text or q.grade,
                rank=pricing.GRADES.index(q.grade) if q.grade else None,
                year=q.year,
                kind=q.kind,
                url=q.url,
            )
        )
    melt_now = melt["value"] if melt else None
    pure_g = melt["pure_metal_g"] if melt else None
    pricing.prepare(points, melt["metal"] if melt else None, pure_g, melt_now, metals.convert(1, "USD", currency))
    table = pricing.price_table(points, melt_now)
    est = pricing.estimate(table, coin.grade, melt_now)

    result["price_table"] = [pricing.to_dict(r) for r in table]
    result["market_quotes"] = [pricing.to_dict(p) for p in points if not p.source.startswith("catalog:")]
    same_set = {r["id"] for r in same_rows}
    comparables = catalog.comparables(catalog_db, coin, currency)
    result["comparables"] = sorted(comparables, key=lambda c: c["id"] not in same_set)

    if est is not None:
        sources = [
            {"source": p.source.removeprefix("catalog:"), "grade": p.grade, "year": p.year or "undated", "kind": p.kind}
            for p in points
        ]
        try:
            explanation = identify.explain(
                {
                    "coin": coin.title,
                    "grade": coin.grade,
                    "melt": melt_now,
                    "currency": currency,
                    "table": [(r.grade, r.retail, r.resale) for r in table if r.retail],
                    "estimate": pricing.to_dict(est),
                    "sources": sources,
                },
                language,
            )
        except Exception as e:
            log.warning("explanation failed: %s", e)
            explanation = ""
        lap("explained")
        result["valuation"] = {
            "value_low": est.value_low,
            "value_high": est.value_high,
            "retail_low": est.retail_low,
            "retail_high": est.retail_high,
            "best_match_ids": sorted(same_set),
            "explanation": explanation,
        }
    return result
