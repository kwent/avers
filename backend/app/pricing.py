"""Deterministic price estimate from market data (catalog listings + web quotes). No LLM here.

Every data point is a retail-level price (dealer asking price, or auction result) for the same coin in some grade.
Old prices of precious-metal coins are brought to today's metal price (price = melt + premium, the premium is
kept), then each grade gets a weighted median. What a private seller can expect is RESALE_FACTOR of that.
"""

import re
from dataclasses import dataclass
from datetime import date

from app.metals import TROY_OZ_G

GRADES = ["B", "TB", "TTB", "SUP", "SPL", "FDC"]
RESALE_FACTOR = 0.8  # dealers buy ~20% under their selling price
MELT_PREMIUM = 1.05  # a coin never sells under its metal value plus a small premium
# Backtest (bench/pricing.py): old prices predict today's within ~15-18% when the newest is under 7 years old and
# there are several; a single price, or only prices 7+ years old, miss by ~40% and come out too high. Such an
# estimate's range reaches down by LOW_CONFIDENCE_SPREAD.
STALE_AGE = 7  # years
LOW_CONFIDENCE_SPREAD = 1.4

# Approximate LBMA annual averages, USD/oz (2025 is approximate). Used only to strip the metal content out of
# dated historical prices; today's price always comes from the live spot.
GOLD_USD_BY_YEAR = {
    2010: 1225, 2011: 1572, 2012: 1669, 2013: 1411, 2014: 1266, 2015: 1160, 2016: 1251, 2017: 1257,
    2018: 1268, 2019: 1393, 2020: 1770, 2021: 1799, 2022: 1800, 2023: 1941, 2024: 2386, 2025: 3400,
}  # fmt: skip
SILVER_USD_BY_YEAR = {
    2010: 20.2, 2011: 35.1, 2012: 31.2, 2013: 23.8, 2014: 19.1, 2015: 15.7, 2016: 17.1, 2017: 17.1,
    2018: 15.7, 2019: 16.2, 2020: 20.6, 2021: 25.1, 2022: 21.7, 2023: 23.4, 2024: 28.3, 2025: 38.0,
}  # fmt: skip


@dataclass
class Point:
    source: str  # "catalog:<source>" or a web site name
    price: float  # in the target currency, as listed
    grade: str | None  # source wording
    rank: float | None  # position on GRADES (0 = B … 5 = FDC); half grades allowed
    year: int | None  # year of the price
    kind: str  # "listing" (asking) or "sold"
    url: str | None = None
    name: str | None = None  # what the source calls it (listing title)
    adjusted: float | None = None  # price at today's metal value
    weight: float = 0.0


def grade_rank(grade: str | None) -> float | None:
    """'TTB-SUP' -> 2.5, 'TTB+' -> 2.3, 'presque SUP' -> 2.7, 'Flan bruni' / unknown -> None."""
    if not grade:
        return None
    g = grade.upper().replace("PRESQUE", "PR.").replace(" ", "")
    tokens = [t for t in re.split(r"[-/]", g.replace("PR.", "")) if t]
    ranks = []
    for t in tokens:
        base = t.rstrip("+")
        if base in GRADES:
            ranks.append(GRADES.index(base) + (0.3 if t.endswith("+") else 0))
    if not ranks:
        return None
    rank = sum(ranks) / len(ranks)
    return rank - 0.3 if g.startswith("PR.") else rank


def metal_value_then(metal: str | None, pure_g: float | None, year: int | None, usd_to_cur: float) -> float | None:
    """Metal content value in the target currency at `year`'s average price (None if not a precious metal)."""
    table = {"gold": GOLD_USD_BY_YEAR, "silver": SILVER_USD_BY_YEAR}.get(metal or "")
    if not table or not pure_g or not year:
        return None
    usd = table[min(max(year, min(table)), max(table))]
    return pure_g * usd / TROY_OZ_G * usd_to_cur


def _weighted_quantile(values: list[float], weights: list[float], q: float) -> float:
    pairs = sorted(zip(values, weights, strict=True))
    total = sum(w for _, w in pairs)
    acc = 0.0
    for v, w in pairs:
        acc += w
        if acc >= q * total:
            return v
    return pairs[-1][0]


def prepare(
    points: list[Point], metal: str | None, pure_g: float | None, melt_now: float | None, usd_to_cur: float
) -> list[Point]:
    """Fill adjusted price and weight. Recent and sold prices weigh more; undated ones little."""
    this_year = date.today().year
    for p in points:
        p.adjusted = p.price
        then = metal_value_then(metal, pure_g, p.year, usd_to_cur)
        if then is not None and melt_now is not None and p.year and p.year < this_year:
            p.adjusted = max(melt_now, p.price - then + melt_now)  # keep the numismatic premium
        age = this_year - p.year if p.year else None
        p.weight = 0.3 if age is None else 1 / (1 + max(age, 0) / 3)
        if p.kind == "sold":
            p.weight *= 1.5
    return points


@dataclass
class GradePrice:
    grade: str
    retail: float | None
    resale: float | None
    points: int


def price_table(points: list[Point], melt_now: float | None) -> list[GradePrice]:
    rows = []
    for i, g in enumerate(GRADES):
        vals, ws = [], []
        for p in points:
            if p.rank is None or abs(p.rank - i) > 0.5:
                continue
            share = 1.0 if abs(p.rank - i) < 0.5 else 0.5  # half grades count for both neighbours
            vals.append(p.adjusted)
            ws.append(p.weight * share)
        retail = _weighted_quantile(vals, ws, 0.5) if vals else None
        rows.append(GradePrice(g, retail, None, len(vals)))
    _interpolate(rows)
    floor = melt_now or 0.0
    for r in rows:
        if r.retail is not None:
            r.retail = round(max(r.retail, floor * MELT_PREMIUM), 0)
            r.resale = round(max(r.retail * RESALE_FACTOR, floor), 0)
    return rows


def _interpolate(rows: list[GradePrice]) -> None:
    """Fill grade gaps between two known grades geometrically (prices rise multiplicatively with grade)."""
    known = [i for i, r in enumerate(rows) if r.retail is not None]
    for a, b in zip(known, known[1:], strict=False):
        for i in range(a + 1, b):
            t = (i - a) / (b - a)
            rows[i].retail = rows[a].retail * (rows[b].retail / rows[a].retail) ** t


def low_confidence(points: list[Point]) -> bool:
    """Too little or too old data for a tight estimate (see LOW_CONFIDENCE_SPREAD)."""
    dated = [p.year for p in points if p.year]
    return len(points) < 2 or not dated or date.today().year - max(dated) >= STALE_AGE


@dataclass
class Estimate:
    grade: str
    value_low: float
    value_high: float
    retail_low: float
    retail_high: float


def estimate(
    rows: list[GradePrice],
    grade: str | None,
    melt_now: float | None,
    uncertain: bool = False,
    upper: str | None = None,
) -> Estimate | None:
    """Range for the estimated grade: from half a grade below to half a grade above, never under melt. A coin read
    between two grades (`upper`, the next one up) spans their two prices instead. `uncertain` (low_confidence data):
    the range reaches down by LOW_CONFIDENCE_SPREAD."""
    if grade not in GRADES:
        return None
    i = GRADES.index(grade)
    row = rows[i]
    if row.retail is None:
        # Graded below every listed grade: no price of its own, but bounded by data. It is worth more than its metal
        # and less than the lowest listed grade above it. (Above every listed grade there is no upper bound: no price.)
        higher = next((r for r in rows[i + 1 :] if r.retail is not None), None)
        if higher is None or not melt_now:
            return None
        return Estimate(
            grade=grade,
            value_low=round(melt_now, 0),
            value_high=higher.resale,
            retail_low=round(melt_now * MELT_PREMIUM, 0),
            retail_high=higher.retail,
        )
    below = rows[i - 1].retail if i > 0 and rows[i - 1].retail else row.retail
    above = rows[i + 1].retail if i + 1 < len(rows) and rows[i + 1].retail else row.retail
    if upper is not None and i + 1 < len(rows) and GRADES[i + 1] == upper and rows[i + 1].retail:
        retail_low, retail_high = sorted((row.retail, rows[i + 1].retail))  # TB-TTB: from the TB to the TTB price
    else:
        # geometric midpoints between grades; listings do not always rise with the grade (an old listing with a big
        # premium can top a better coin's), so the range is ordered
        retail_low, retail_high = sorted(((below * row.retail) ** 0.5, (above * row.retail) ** 0.5))
    floor = melt_now or 0.0
    if uncertain:
        retail_low = max(retail_low / LOW_CONFIDENCE_SPREAD, floor * MELT_PREMIUM)
    return Estimate(
        grade=grade,
        value_low=round(max(retail_low * RESALE_FACTOR, floor), 0),
        value_high=round(max(retail_high * RESALE_FACTOR, floor), 0),
        retail_low=round(retail_low, 0),
        retail_high=round(retail_high, 0),
    )
