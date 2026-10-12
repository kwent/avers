from app import identify, main, pipeline
from tests.test_api import jpeg
from tests.test_catalog import make_coin


def run(monkeypatch, reading):
    monkeypatch.setattr(identify, "identify", lambda images, language: reading)
    return pipeline.run([(jpeg(), "f.jpg")], "EUR", "fr", main.catalog_db, main.collection_db, None)


def test_catalog_entry_is_the_source_of_truth(monkeypatch, catalog_1851):
    est = run(monkeypatch, make_coin(weight_g=3.0, catalog_refs=["G. 1012"]))
    assert est["match"]["id"] in catalog_1851
    assert "reference" in est["match"]["criteria"]
    assert est["identification"]["weight_g"] == 3.22  # catalog wins over the reading
    table = {r["grade"]: r for r in est["price_table"]}
    assert (table["TTB"]["retail"], table["SUP"]["retail"]) == (600, 1000)
    assert est["valuation"]["retail_low"] == 600  # graded TTB
    assert est["valuation"]["basis"]["listings"] == 2


def test_no_catalog_listing_means_no_price(monkeypatch, catalog_1851):
    est = run(monkeypatch, make_coin(year=1850))  # nothing listed for 1850
    assert est["match"] is None
    assert est["valuation"] is None
    assert est["melt"] is not None  # the metal value is still known
