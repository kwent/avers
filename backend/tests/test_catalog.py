import pytest

from app import catalog
from app.db import connect, upsert_coin
from app.identify import CoinIdentification


def make_coin(**kw) -> CoinIdentification:
    base = dict(
        is_coin=True,
        title="10 Francs Cérès 1851 A",
        country_iso="FR",
        country_name="France",
        year=1851,
        mint_mark="A",
        face_value=10,
        denomination="10 Francs",
        type_name="Cérès",
        metal="gold",
        fineness=0.9,
        weight_g=3.2258,
        catalog_refs=["G. 1012"],
        grade="TTB",
        grade_notes="",
        confidence=0.9,
        authenticity_notes=None,
        notes="",
    )
    return CoinIdentification(**{**base, **kw})


@pytest.fixture
def db(tmp_path):
    db = connect(tmp_path / "coins.sqlite")
    rows = [
        ("1", "FRANCE-1851A-10 Francs G. 1012 TTB", 1851, 10, "Or", "TTB", 900),
        ("2", "FRANCE-1850A-10 Francs G. 1012 SUP", 1850, 10, "Or", "SUP", 1100),
        ("3", "FRANCE-1867A-10 Francs G. 1015 TTB", 1867, 10, "Or", "TTB", 400),
        ("4", "FRANCE-1851-10 Centimes", 1851, 10, "Bronze", "TB", 20),
        ("5", "ITALIE-1851-10 Lire", 1851, 10, "Or", "TTB", 700),
    ]
    for sid, name, year, face, metal, grade, price in rows:
        upsert_coin(
            db,
            {
                "source": "test",
                "source_id": sid,
                "name": name,
                "url": f"https://example.com/{sid}",
                "country_iso": "IT" if "ITALIE" in name else "FR",
                "year": year,
                "face_value": face,
                "metal": metal,
                "grade": grade,
                "price": price,
                "currency": "EUR",
                "in_stock": 1,
            },
            [(0, f"https://example.com/{sid}.jpg")],
        )
    db.commit()
    return db


def test_comparables_ranks_same_reference_and_year_first(db):
    names = [c["name"] for c in catalog.comparables(db, make_coin(), "EUR")]
    assert names[0].startswith("FRANCE-1851A")
    assert names[1].startswith("FRANCE-1850A")


def test_comparables_excludes_other_country_and_wrong_metal(db):
    names = [c["name"] for c in catalog.comparables(db, make_coin(), "EUR")]
    assert not any("ITALIE" in n or "Centimes" in n for n in names)


def test_comparables_converts_currency(db):
    top = catalog.comparables(db, make_coin(), "USD")[0]
    assert top["currency"] == "USD"
    assert top["price"] == pytest.approx(1000)


def test_comparables_empty_for_non_coin(db):
    assert catalog.comparables(db, make_coin(is_coin=False), "EUR") == []


@pytest.mark.parametrize(
    "grade,rank",
    [("TTB", 2), ("TTB-SUP", 2.5), ("TTB+", 2.3), ("presque SUP", 2.7), ("FDC", 5), ("Flan bruni", None), (None, None)],
)
def test_grade_rank(grade, rank):
    assert catalog._grade_rank(grade) == (pytest.approx(rank) if rank is not None else None)


def test_gadoury_numbers():
    assert catalog._gadoury_numbers(["G. 1012", "KM 770", "Gad.1015", "G 52"]) == ["1012", "1015", "52"]
