"""Find the catalog entry for a coin read from photos — plain rules + visual similarity, no LLM.

The photo reading gives country, denomination, year, mint and references. Catalog listings with the same
country, face value and year (and mint / Gadoury reference when both sides know them) are the same coin in
various grades; visual similarity confirms the type and picks the closest listing.
"""

import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field

from app.identify import CoinIdentification
from app.metals import CATALOG_METALS

# Visual similarity (DINOv2, 0-1) needed to accept a match on facts alone, and how far below the best listing
# another listing may score and still count as the same type.
MIN_SIMILARITY = 0.75
SAME_TYPE_MARGIN = 0.05

# "FRANCE-1851A-10 Francs …", "FRANCE-1717 W-Ecu …", "FRANCE-1854-A-10 FRANCS …", "HONGRIE-1911 KB-10 Korona …"
LISTING_DATE = re.compile(r"-(\d{4})(?:/\d+)?(?:\s*-?\s*([A-Z]{1,2}))?(?=\s*-)")
GADOURY_REF = re.compile(r"\bG(?:ad(?:oury)?)?\.?\s*(\d+[a-z]?)\b", re.I)
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


def listing_mint(name: str) -> str | None:
    m = LISTING_DATE.search(name or "")
    return m.group(2) if m else None


def gadoury_refs(refs: list[str]) -> set[str]:
    out = set()
    for ref in refs:
        m = GADOURY_REF.match(ref.strip())
        if m:
            out.add(m.group(1).lower())
    return out


def listing_refs(name: str | None) -> set[str]:
    """Gadoury numbers quoted in a listing name, e.g. 'FRANCE-1851A-10 Francs G. 1012 TTBSUP' -> {'1012'}."""
    return {x.lower() for x in GADOURY_REF.findall(name or "")}


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
        rows = [r for r in rows if listing_mint(r["name"]) in (None, mint)]
        if any(listing_mint(r["name"]) == mint for r in rows):
            criteria.append("mint")
    refs = gadoury_refs(coin.catalog_refs)
    if refs:
        with_ref = [r for r in rows if listing_refs(r["name"]) & refs]
        if with_ref:
            rows = with_ref
            criteria.append("reference")
    return rows, criteria


def find(db: sqlite3.Connection, coin: CoinIdentification, photos: list[bytes], index=None) -> Match | None:
    rows, criteria = candidates(db, coin)
    if not rows:
        return None
    sims = index.scores(photos, [r["id"] for r in rows]) if index is not None and len(index) else {}
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


# Digits a worn or blurry date mixes up, most likely first.
CONFUSABLE_DIGITS = ["56", "38", "68", "08", "06", "17", "35", "69", "09", "47"]


def _misread_rank(read: int, year: int) -> int | None:
    """How plausible it is that `year` was read as `read`: one confusable digit apart (lower is likelier)."""
    a, b = str(read), str(year)
    diffs = [(x, y) for x, y in zip(a, b, strict=False) if x != y]
    if len(a) != len(b) or len(diffs) != 1:
        return None
    pair = "".join(sorted(diffs[0]))
    return CONFUSABLE_DIGITS.index(pair) if pair in CONFUSABLE_DIGITS else None


def year_suggestions(db: sqlite3.Connection, coin: CoinIdentification, limit: int = 3) -> list[int]:
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
    words = [w for w in _plain(coin.type_name or "").split() if len(w) >= 4]
    ranked: dict[int, tuple[int, int]] = {}
    for r in rows:
        rank = _misread_rank(coin.year, r["year"])
        if rank is None or (metals and r["metal"] and r["metal"] not in metals):
            continue
        typed = 0 if any(w in _plain(r["name"]) for w in words) else 1
        ranked[r["year"]] = min(ranked.get(r["year"], (2, 99)), (typed, rank))
    return sorted(ranked, key=ranked.get)[:limit]


def _plain(text: str) -> str:
    """Lower case without accents, for loose name matching ("CÉRÉS" ~ "Cérès")."""
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c))
