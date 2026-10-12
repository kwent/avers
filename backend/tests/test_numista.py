import io
import json

import pytest

from app import main, numista
from tests.test_api import client, jpeg
from tests.test_catalog import make_coin

CERES = {"id": 1711, "title": "10 Francs Cérès", "issuer": {"name": "France"}, "min_year": 1850, "max_year": 1899}
ISSUES = [
    {"id": 1, "gregorian_year": 1850, "mint_letter": "A", "mintage": 1_000_000},
    {"id": 2, "gregorian_year": 1851, "mint_letter": "A", "mintage": 4_000_000},
    {"id": 3, "gregorian_year": 1895, "mint_letter": "A", "mintage": 1_200_000},
]


@pytest.fixture
def fake_numista(monkeypatch):
    """Numista answers from fixtures; records the paths it was asked."""
    asked = []

    def get(store, path, params, max_age):
        asked.append(path)
        if path == "/types":
            return {"count": 1, "types": [CERES]}
        if path == "/types/1711/issues":
            return ISSUES
        if path.endswith("/prices"):
            return {"currency": "EUR", "prices": [{"grade": "vf", "price": 700}, {"grade": "xf", "price": 900}]}
        return None

    monkeypatch.setattr(numista, "KEY", "test")
    monkeypatch.setattr(numista, "_get", get)
    monkeypatch.setattr(numista, "_lists", {})
    return asked


def estimate_of(monkeypatch, **coin):
    monkeypatch.setattr(main.identify, "identify", lambda images, language: make_coin(**coin))
    return client.post("/estimate", files={"front": ("f.jpg", jpeg(), "image/jpeg")}).json()


def test_year_struck_but_not_listed_is_priced_by_numista(monkeypatch, fake_numista):
    est = estimate_of(monkeypatch, year=1851, catalog_refs=[])  # no Gadoury listing in the test catalog
    assert est["year_check"] is None  # Numista knows 1851 A: nothing to ask
    assert est["numista"]["issue"] == {"id": 2, "mintage": 4_000_000, "mint": "A"}
    # Numista's grade prices go through the same pricing as listings: TTB = "vf" 700 €, SUP = "xf" 900 €
    table = {r["grade"]: r["retail"] for r in est["price_table"]}
    assert (table["TTB"], table["SUP"]) == (700, 900)
    v = est["valuation"]
    assert (v["retail_low"], v["retail_high"]) == (700, 794)  # half a grade either side, geometric
    assert v["value_low"] == 560  # what a private seller gets: RESALE_FACTOR of the shop price
    assert v["source"] == "numista"


def test_year_never_struck_asks_with_numistas_years(monkeypatch, fake_numista):
    est = estimate_of(monkeypatch, year=1861, catalog_refs=[])
    assert est["year_check"] == {"read": 1861, "suggestions": [1851, 1850, 1895]}
    assert est["valuation"] is None


def test_catalog_match_does_not_spend_numista_quota(monkeypatch, fake_numista, catalog_1851):
    est = estimate_of(monkeypatch)
    assert est["valuation"]["retail_low"] == 600 and est["numista"] is None
    assert fake_numista == []


def test_get_caches_and_respects_the_monthly_quota(monkeypatch):
    calls = []

    def urlopen(req, timeout, context):
        calls.append(req.full_url)
        assert req.get_header("Numista-api-key") == "test"
        return io.BytesIO(json.dumps({"count": 0, "types": []}).encode())

    monkeypatch.setattr(numista, "KEY", "test")
    monkeypatch.setattr(numista.urllib.request, "urlopen", urlopen)
    store = main.store
    params = {"q": f"cache-test-{id(calls)}"}
    assert numista._get(store, "/types", params, numista.FACTS_AGE) == {"count": 0, "types": []}
    assert numista._get(store, "/types", params, numista.FACTS_AGE) == {"count": 0, "types": []}
    assert len(calls) == 1  # second answer from the cache

    monkeypatch.setattr(numista, "MAX_PER_MONTH", 0)
    assert numista._get(store, "/types", {"q": "over quota"}, numista.FACTS_AGE) is None
    assert len(calls) == 1


def test_disabled_without_key(monkeypatch):
    monkeypatch.setattr(numista, "KEY", "")
    assert numista._get(main.store, "/types", {}, numista.FACTS_AGE) is None


def test_a_wrong_gadoury_number_falls_back_to_text_search(monkeypatch):
    """The reading quotes G. 476 (the 1 Franc de Gaulle) for a 10 Francs Cérès: that type is not taken."""
    de_gaulle = {"id": 99, "title": "1 Franc (Charles de Gaulle)", "min_year": 1988, "max_year": 1988}

    def get(store, path, params, max_age):
        if path == "/catalogues":
            return {"catalogues": [{"id": 109, "title": "Monnaies françaises", "author": "Gadoury"}]}
        if path == "/types":
            return {"types": [de_gaulle] if "number" in params else [CERES]}
        return None

    monkeypatch.setattr(numista, "KEY", "test")
    monkeypatch.setattr(numista, "_get", get)
    monkeypatch.setattr(numista, "_lists", {})
    coin = make_coin(catalog_refs=["G. 476"])
    assert numista.find_type(None, coin)["id"] == CERES["id"]
