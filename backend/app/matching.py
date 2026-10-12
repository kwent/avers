"""Find the catalog entry for a coin read from photos — plain rules + visual similarity, no LLM.

The photo reading gives country, denomination, year, mint and references. Catalog listings with the same
country, face value and year (and mint / Gadoury reference when both sides know them) are the same coin in
various grades; visual similarity confirms the type and picks the closest listing.
"""

import re
import sqlite3
from dataclasses import dataclass, field

from app.identify import CoinIdentification
from app.listing import gadoury_refs, plain, stored_refs
from app.metals import CATALOG_METALS

# Visual similarity (DINOv2, 0-1) needed to accept a match on facts alone, and how far below the best listing
# another listing may score and still count as the same type.
MIN_SIMILARITY = 0.75
SAME_TYPE_MARGIN = 0.05

LEADING_NUMBER = re.compile(r"^\s*(\d+(?:[.,]\d+)?)")


def face_values(coin: CoinIdentification) -> list[float]:
    """Face values the catalog may record for this coin.

    The catalog is inconsistent about sub-units ('20 CENTIMES' is stored as 20 or as 0.2), and readings vary the
    same way, so accept both the reading's face value and the number written in its denomination.
    """
    out = [] if coin.face_value is None else [coin.face_value]
    m = LEADING_NUMBER.match(coin.denomination or "")
    if m:
        n = float(m.group(1).replace(",", "."))
        if n not in out:
            out.append(n)
    return out


@dataclass
class Match:
    row: sqlite3.Row
    same: list[sqlite3.Row]  # every listing of this coin (any grade), match included
    confidence: float
    criteria: list[str] = field(default_factory=list)  # what agreed: country, face_value, year, mint, reference
    similarity: float | None = None


def candidates(db: sqlite3.Connection, coin: CoinIdentification) -> tuple[list[sqlite3.Row], list[str]]:
    """Listings agreeing with the reading on every fact both sides know."""
    if coin.status != "identified" or not coin.country_iso or not coin.year:
        return [], []
    where = ["country_iso = ?", "year = ?", "price > 0"]
    params: list = [coin.country_iso.upper(), coin.year]
    criteria = ["country", "year"]
    faces = face_values(coin)
    if faces:
        where.append(f"face_value IN ({', '.join('?' * len(faces))})")
        params += faces
        criteria.append("face_value")
    rows = db.execute(f"SELECT * FROM coins WHERE {' AND '.join(where)}", params).fetchall()

    metals = CATALOG_METALS.get(coin.metal, [])
    if metals:
        rows = [r for r in rows if not r["metal"] or r["metal"] in metals]
    if coin.mint_mark:
        mint = coin.mint_mark.strip().upper()
        rows = [r for r in rows if r["mint"] in (None, mint)]
        if any(r["mint"] == mint for r in rows):
            criteria.append("mint")
    refs = gadoury_refs(coin.catalog_refs)
    if refs:
        with_ref = [r for r in rows if stored_refs(r["gadoury"]) & refs]
        if with_ref:
            rows = with_ref
            criteria.append("reference")
    return rows, criteria


def find(db: sqlite3.Connection, coin: CoinIdentification, queries: list, index=None) -> Match | None:
    """queries: the photos' query vectors (visual.Index.query), when there is a visual index."""
    rows, criteria = candidates(db, coin)
    if not rows:
        return None
    sims = index.scores(queries, [r["id"] for r in rows]) if index is not None and len(index) and queries else {}
    if sims:
        best_id = max(sims, key=sims.get)
        best = sims[best_id]
        if best < MIN_SIMILARITY and "reference" not in criteria:
            return None  # the facts agree but the photos do not look like it: do not trust it
        row = next(r for r in rows if r["id"] == best_id)
        same = [r for r in rows if r["id"] not in sims or sims[r["id"]] >= best - SAME_TYPE_MARGIN]
        confidence = min(0.99, best + (0.05 if "reference" in criteria else 0))
        return Match(row, same, round(confidence, 2), criteria + ["photo"], round(best, 3))
    # no visual index (or no catalog photos): facts only, trusted when a catalog reference agrees
    if "reference" not in criteria:
        return None
    row = max(rows, key=lambda r: (r["in_stock"] or 0, r["modified"] or ""))
    return Match(row, rows, 0.8, criteria)


def type_words(coin: CoinIdentification) -> list[str]:
    """Words of the type name ("Cérès", "Napoléon III") to recognise the type in catalog listing names."""
    return [w for w in plain(coin.type_name).split() if len(w) >= 4]


def type_rows(db: sqlite3.Connection, coin: CoinIdentification) -> list[sqlite3.Row]:
    """Catalog listings of any year with the coin's country, face value and metal: its type and its look-alikes."""
    faces = face_values(coin)
    if coin.status != "identified" or not coin.country_iso or not faces:
        return []
    rows = db.execute(
        "SELECT year, name, metal, price, gadoury FROM coins"
        f" WHERE country_iso = ? AND face_value IN ({', '.join('?' * len(faces))})",
        [coin.country_iso.upper(), *faces],
    ).fetchall()
    metals = CATALOG_METALS.get(coin.metal, [])
    return [r for r in rows if not metals or not r["metal"] or r["metal"] in metals]


def type_refs(db: sqlite3.Connection, coin: CoinIdentification, limit: int = 3) -> list[str]:
    """Gadoury numbers of catalog listings of the coin's type (same country, face value and metal, the type named in
    the listing), nearest years first, as "G. 1012". Lets a reading without a reference, or with a misread year, be
    looked up by number elsewhere."""
    words = type_words(coin)
    if not words:
        return []
    ranked: dict[str, int] = {}
    for r in type_rows(db, coin):
        if not any(w in plain(r["name"]) for w in words):
            continue
        gap = abs((r["year"] or 0) - (coin.year or 0)) if coin.year else 0
        for ref in stored_refs(r["gadoury"]):
            ranked[ref] = min(ranked.get(ref, gap), gap)
    return [f"G. {ref}" for ref in sorted(ranked, key=ranked.get)[:limit]]
