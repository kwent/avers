"""Backtest the pricing rules on the catalog's own history: how well do older prices predict today's?

For every French gold coin (country, year, face value, mint) with listings dated in TEST_YEARS and older ones, each
rule prices the recent listing's grade from the older listings only (app.pricing, the production code), and the
prediction is compared with the recent price. Scores: median absolute error and median bias, in %.

Rules compared (how an old price is brought to the test year):
- raw: the old price as it is
- keep_premium: metal value then -> metal value now, the premium kept in euros (the rule until now)
- scale: the whole price scaled with the metal price
- decay: like keep_premium, the premium halving every PREMIUM_HALF_LIFE years

Run from backend/ (needs data/coins.sqlite): uv run python -m bench.pricing
"""

import math
import statistics
from collections import defaultdict
from datetime import date

from app import metals, pricing
from app.db import connect
from app.pipeline import _year

TEST_YEARS = (2025, 2026)
FINENESS = 0.9  # French gold francs (Louis d'or: 0.917, close enough here)
HALF_LIVES = (1, 2, 3, 5)  # weight half-life of a price, in years
PREMIUM_HALF_LIFE = 8


def metal_value(pure_g: float, year: int, usd_to_eur: float, spot_now: float) -> float:
    if year >= date.today().year:
        return pure_g * spot_now / pricing.TROY_OZ_G * usd_to_eur
    return pricing.metal_value_then("gold", pure_g, year, usd_to_eur)


def adjust(rule: str, price: float, then: float, now: float, age: int) -> float:
    if rule == "raw":
        return price
    if rule == "scale":
        return price * now / then
    premium = price - then
    if rule == "decay":
        premium *= 0.5 ** (age / PREMIUM_HALF_LIFE)
    return max(now, premium + now)


def predict(train: list, grade_rank: float, target_year: int, rule: str, half_life: float, ctx) -> float | None:
    usd_to_eur, spot_now = ctx
    points = []
    for p in train:
        then = metal_value(p["pure_g"], p["year"], usd_to_eur, spot_now)
        now = metal_value(p["pure_g"], target_year, usd_to_eur, spot_now)
        age = target_year - p["year"]
        points.append(
            pricing.Point(
                source="test",
                price=p["price"],
                grade=p["grade"],
                rank=p["rank"],
                year=p["year"],
                kind=p["kind"],
                adjusted=adjust(rule, p["price"], then, now, age),
                weight=0.5 ** (age / half_life) * (1.5 if p["kind"] == "sold" else 1.0),
            )
        )
    melt = metal_value(train[0]["pure_g"], target_year, usd_to_eur, spot_now)
    rows = pricing.price_table(points, melt)
    row = rows[round(grade_rank)] if 0 <= round(grade_rank) < len(rows) else None
    return row.retail if row else None


def main() -> None:
    db = connect()
    rows = db.execute(
        "SELECT country_iso, year, face_value, mint, grade, price, weight_g, in_stock, created, modified FROM coins"
        " WHERE country_iso = 'FR' AND metal = 'Or' AND price > 0 AND weight_g > 0 AND year IS NOT NULL"
    ).fetchall()
    groups = defaultdict(list)
    for r in rows:
        rank = pricing.grade_rank(r["grade"])
        when = _year(r["modified"] or r["created"])
        if rank is None or when is None:
            continue
        key = (r["year"], r["face_value"], r["mint"])
        groups[key].append(
            {
                "price": r["price"],
                "grade": r["grade"],
                "rank": rank,
                "year": when,
                "kind": "listing" if r["in_stock"] else "sold",
                "pure_g": r["weight_g"] * FINENESS,
            }
        )
    ctx = (metals.convert(1, "USD", "EUR"), metals.spot_usd_per_oz("gold"))
    cases = []
    for listings in groups.values():
        train = [p for p in listings if p["year"] < TEST_YEARS[0]]
        for t in (p for p in listings if p["year"] in TEST_YEARS):
            if train:
                cases.append((train, t))
    print(f"{len(cases)} recent listings with older listings of the same coin, {len(groups)} coins\n")
    print(f"{'rule':<13} {'half-life':>9} {'n':>5} {'median |error|':>15} {'median bias':>12} {'within 15%':>11}")
    for rule in ("raw", "keep_premium", "scale", "decay"):
        for half_life in HALF_LIVES:
            errors = []
            for train, t in cases:
                pred = predict(train, t["rank"], t["year"], rule, half_life, ctx)
                if pred:
                    errors.append(math.log(pred / t["price"]))
            if not errors:
                continue
            abs_err = statistics.median(abs(e) for e in errors)
            bias = statistics.median(errors)
            within = sum(abs(e) < math.log(1.15) for e in errors) / len(errors)
            print(
                f"{rule:<13} {half_life:>8}y {len(errors):>5} {math.exp(abs_err) - 1:>14.0%} "
                f"{math.exp(bias) - 1:>+11.0%} {within:>10.0%}"
            )


if __name__ == "__main__":
    main()
