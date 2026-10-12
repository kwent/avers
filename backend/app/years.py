"""Dates read from photos can be wrong (a worn 5 taken for a 6). When the year read has no catalog listing, or was
never struck, the app asks the user which year the coin shows, suggesting the likeliest real years. Plain code."""

import sqlite3

from app.identify import CoinIdentification
from app.matching import face_values, plain
from app.metals import CATALOG_METALS

# Digits a worn or blurry date mixes up, most likely first.
CONFUSABLE_DIGITS = ["56", "38", "68", "08", "06", "17", "35", "69", "09", "47"]


def misread_rank(read: int, year: int) -> int | None:
    """How plausible it is that `year` was read as `read`: one confusable digit apart (lower is likelier)."""
    a, b = str(read), str(year)
    diffs = [(x, y) for x, y in zip(a, b, strict=False) if x != y]
    if len(a) != len(b) or len(diffs) != 1:
        return None
    pair = "".join(sorted(diffs[0]))
    return CONFUSABLE_DIGITS.index(pair) if pair in CONFUSABLE_DIGITS else None


def catalog_suggestions(db: sqlite3.Connection, coin: CoinIdentification, limit: int = 3) -> list[int]:
    """Catalogued years the coin may really be from, when the year read has no listing: same country, face value
    and metal, and one commonly misread digit away (a worn 5 taken for a 6). Years whose listings name the coin
    type come first."""
    faces = face_values(coin)
    if coin.status != "identified" or not coin.country_iso or not coin.year or not faces:
        return []
    rows = db.execute(
        f"SELECT year, name, metal FROM coins WHERE country_iso = ? AND face_value IN ({', '.join('?' * len(faces))})"
        " AND year IS NOT NULL AND price > 0",
        [coin.country_iso.upper(), *faces],
    ).fetchall()
    metals = CATALOG_METALS.get(coin.metal, [])
    words = [w for w in plain(coin.type_name or "").split() if len(w) >= 4]
    ranked: dict[int, tuple[int, int]] = {}
    for r in rows:
        rank = misread_rank(coin.year, r["year"])
        if rank is None or (metals and r["metal"] and r["metal"] not in metals):
            continue
        typed = 0 if any(w in plain(r["name"]) for w in words) else 1
        ranked[r["year"]] = min(ranked.get(r["year"], (2, 99)), (typed, rank))
    return sorted(ranked, key=ranked.get)[:limit]


def check(catalog_db: sqlite3.Connection, coin: CoinIdentification, ref: dict | None) -> dict | None:
    """Ask the user which year the coin shows when the year read may be wrong. Numista lists the years its type was
    really struck: a year it knows is not questioned. Suggestions pool Numista's years and the catalog's, a commonly
    misread digit away first, then the nearest struck years."""
    numista_years = ref["years"] if ref else []
    if coin.year in numista_years:
        return None
    pool = set(numista_years) | set(catalog_suggestions(catalog_db, coin))
    confusable = sorted(
        (y for y in pool if misread_rank(coin.year, y) is not None),
        key=lambda y: misread_rank(coin.year, y),
    )
    nearest = sorted((y for y in pool if y not in confusable), key=lambda y: abs(y - coin.year))
    return {"read": coin.year, "suggestions": (confusable + nearest)[:3]}
