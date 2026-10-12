"""Find catalog listings comparable to an identified coin."""

import re
import sqlite3

from app.identify import CoinIdentification
from app.matching import face_values
from app.metals import CATALOG_METALS, convert
from app.pricing import grade_rank


def _gadoury_numbers(refs: list[str]) -> list[str]:
    out = []
    for ref in refs:
        m = re.match(r"\s*G(?:ad(?:oury)?)?\.?\s*(?:[A-Z]{2}\s*)?(\d+)", ref, re.I)
        if m:
            out.append(m.group(1))
    return out


def comparables(db: sqlite3.Connection, coin: CoinIdentification, currency: str, limit: int = 15) -> list[dict]:
    if coin.status != "identified":
        return []
    where, params = [], []
    if coin.country_iso:
        where.append("country_iso = ?")
        params.append(coin.country_iso.upper())
    refs = _gadoury_numbers(coin.catalog_refs)
    alt = []
    faces = face_values(coin)
    if faces:
        alt.append(f"face_value IN ({', '.join('?' * len(faces))})")
        params += faces
    for n in refs:
        alt.append("(name LIKE ? OR description LIKE ?)")
        params += [f"%G. {n} %", f"%G. {n}%"]
    if alt:
        where.append("(" + " OR ".join(alt) + ")")
    if not where:
        return []
    rows = db.execute(f"SELECT * FROM coins WHERE {' AND '.join(where)} AND price > 0 LIMIT 2000", params).fetchall()

    metals = CATALOG_METALS.get(coin.metal, [])
    target_grade = grade_rank(coin.grade) if coin.grade != "unknown" else None
    scored = []
    for r in rows:
        text = f"{r['name']} {r['description'] or ''}"
        score = 0.0
        if any(re.search(rf"G\.\s*{n}\b", text) for n in refs):
            score += 4
        if r["face_value"] in faces:
            score += 2
        if metals and r["metal"] in metals:
            score += 1
        elif metals and r["metal"]:
            score -= 3
        if coin.year and r["year"]:
            score += max(0, 3 - abs(r["year"] - coin.year) / 2)
        rank = grade_rank(r["grade"])
        if target_grade is not None and rank is not None:
            score += max(0, 1 - abs(rank - target_grade) / 2)
        if score >= 3:
            scored.append((score, r))
    scored.sort(key=lambda x: (-x[0], -(x[1]["in_stock"] or 0)))

    out = []
    for score, r in scored[:limit]:
        img = (
            r["id"]
            and db.execute(
                "SELECT url, local_path FROM coin_images WHERE coin_id = ? ORDER BY position LIMIT 2", (r["id"],)
            ).fetchall()
        )
        out.append(
            {
                "id": r["id"],
                "source": r["source"],
                "name": r["name"],
                "url": r["url"],
                "year": r["year"],
                "grade": r["grade"],
                "metal": r["metal"],
                "weight_g": r["weight_g"],
                "price": round(convert(r["price"], r["currency"], currency), 2),
                "currency": currency,
                "in_stock": r["in_stock"],
                "listed": (r["modified"] or r["created"] or "")[:10],
                "images": [i["url"] for i in img],
                "score": round(score, 2),
            }
        )
    return out
