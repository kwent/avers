from datetime import date

import pytest

from app import pricing
from app.pricing import Point

THIS_YEAR = date.today().year


def pt(price, grade, year=THIS_YEAR, kind="sold"):
    return Point(source="t", price=price, grade=grade, rank=pricing.grade_rank(grade), year=year, kind=kind)


def table(points, melt=None, metal=None, pure_g=None):
    pricing.prepare(points, metal, pure_g, melt, usd_to_cur=1.0)
    return {r.grade: r for r in pricing.price_table(points, melt)}


def test_weighted_median_per_grade_and_resale_factor():
    rows = table([pt(900, "SUP"), pt(1000, "SUP"), pt(1100, "SUP"), pt(500, "TTB")])
    assert rows["SUP"].retail == 1000
    assert rows["SUP"].resale == 800
    assert rows["TTB"].retail == 500
    assert rows["B"].retail is None


def test_half_grades_count_for_both_neighbours():
    rows = table([pt(700, "TTB-SUP")])
    assert rows["TTB"].retail == rows["SUP"].retail == 700


def test_missing_grade_is_interpolated_geometrically():
    rows = table([pt(400, "TB"), pt(1600, "SUP")])
    assert rows["TTB"].retail == pytest.approx(800, abs=1)


def test_old_gold_price_keeps_premium_at_todays_metal_value():
    # 2014 sale at 400 €: gold then ≈ 1266 $/oz, now 4000 $/oz, 2.9 g fine -> metal 118 € then, 373 € now
    pure_g, melt_now = 2.9, 2.9 * 4000 / pricing.TROY_OZ_G
    points = pricing.prepare([pt(400, "TTB", year=2014)], "gold", pure_g, melt_now, usd_to_cur=1.0)
    then = 2.9 * 1266 / pricing.TROY_OZ_G
    assert points[0].adjusted == pytest.approx(400 - then + melt_now)


def test_recent_and_sold_prices_weigh_more():
    old, recent = pricing.prepare([pt(100, "SUP", year=THIS_YEAR - 9), pt(100, "SUP")], None, None, None, 1.0)
    listing = pricing.prepare([pt(100, "SUP", kind="listing")], None, None, None, 1.0)[0]
    undated = pricing.prepare([pt(100, "SUP", year=None)], None, None, None, 1.0)[0]
    assert recent.weight > listing.weight > old.weight
    assert undated.weight < listing.weight


def test_never_below_melt():
    rows = table([pt(300, "TB")], melt=350)
    assert rows["TB"].retail >= 350
    assert rows["TB"].resale >= 350


def test_estimate_spans_half_a_grade_each_side():
    rows = pricing.price_table(
        pricing.prepare([pt(500, "TTB"), pt(1000, "SUP"), pt(2000, "SPL")], None, None, None, 1.0), None
    )
    est = pricing.estimate(rows, "SUP", None)
    assert est.retail_low == pytest.approx((500 * 1000) ** 0.5, abs=1)
    assert est.retail_high == pytest.approx((1000 * 2000) ** 0.5, abs=1)
    assert est.value_low == pytest.approx(est.retail_low * 0.8, abs=1)


@pytest.mark.parametrize("grade", ["unknown", None, "SPL"])
def test_no_estimate_without_grade_or_data(grade):
    rows = pricing.price_table(pricing.prepare([pt(500, "TTB")], None, None, None, 1.0), None)
    assert pricing.estimate(rows, grade, None) is None
