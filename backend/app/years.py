"""Dates read from photos can be wrong (a worn 5 taken for a 6). When the year read has no catalog listing, or was
never struck, the app asks the user which year the coin shows, suggesting the likeliest real years. Plain code."""

import sqlite3

from app.identify import CoinIdentification
from app.listing import plain
from app.matching import type_rows, type_words

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
    if not coin.year:
        return []
    words = type_words(coin)
    ranked: dict[int, tuple[int, int]] = {}
    for r in type_rows(db, coin):
        rank = misread_rank(coin.year, r["year"]) if r["year"] and (r["price"] or 0) > 0 else None
        if rank is None:
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
    ranks = {y: misread_rank(coin.year, y) for y in pool}
    confusable = sorted((y for y in pool if ranks[y] is not None), key=ranks.get)
    nearest = sorted((y for y in pool if ranks[y] is None), key=lambda y: abs(y - coin.year))
    return {"read": coin.year, "suggestions": (confusable + nearest)[:3]}
