"""Find catalog listings comparable to an identified coin."""

import sqlite3

from app.identify import CoinIdentification
from app.listing import gadoury_refs, stored_refs
from app.matching import face_values
from app.metals import CATALOG_METALS, convert
from app.pricing import grade_rank


def comparables(db: sqlite3.Connection, coin: CoinIdentification, currency: str, limit: int = 15) -> list[dict]:
    if coin.status != "identified":
        return []
    where, params = [], []
    if coin.country_iso:
        where.append("country_iso = ?")
        params.append(coin.country_iso.upper())
    refs = sorted(gadoury_refs(coin.catalog_refs))
    alt = []
    faces = face_values(coin)
    if faces:
        alt.append(f"face_value IN ({', '.join('?' * len(faces))})")
        params += faces
    for n in refs:
        alt.append("gadoury_all LIKE ?")
        params.append(f"% {n} %")
    if alt:
        where.append("(" + " OR ".join(alt) + ")")
    if not where:
        return []
    rows = db.execute(f"SELECT * FROM coins WHERE {' AND '.join(where)} AND price > 0 LIMIT 2000", params).fetchall()

    metals = CATALOG_METALS.get(coin.metal, [])
    target_grade = grade_rank(coin.grade) if coin.grade != "unknown" else None
    scored = []
    for r in rows:
        score = 0.0
        if stored_refs(r["gadoury_all"]) & set(refs):
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

    top = scored[:limit]
    ids = [r["id"] for _, r in top if r["id"]]
    images: dict[int, list[str]] = {}
    marks = ", ".join("?" * len(ids))
    sql = f"SELECT coin_id, url FROM coin_images WHERE coin_id IN ({marks}) ORDER BY coin_id, position"
    for i in db.execute(sql, ids):
        images.setdefault(i["coin_id"], []).append(i["url"])
    out = []
    for score, r in top:
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
                "images": images.get(r["id"], [])[:2],
                "score": round(score, 2),
            }
        )
    return out
