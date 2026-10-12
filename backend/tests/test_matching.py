import pytest

from app import listing, main, matching, years
from tests.test_catalog import make_coin


class FakeIndex:
    def __init__(self, scores):
        self._scores = scores

    def __len__(self):
        return 1

    @staticmethod
    def query(photo):
        return photo

    def scores(self, photos, ids):
        return {i: s for i, s in self._scores.items() if i in ids}


@pytest.mark.parametrize(
    "name,mint,refs",
    [
        ("FRANCE-1851A-10 Francs 2e République G. 1012 TTBSUP", "A", {"1012"}),
        ("FRANCE-1717 W-Ecu Vertugadin-Lille", "W", set()),
        ("FRANCE-1854-A-10 FRANCS-NAPOLEON III", "A", set()),
        ("HONGRIE-1911 KB-10 Korona-PCGS MS61", "KB", set()),
        ("FRANCE-1960-5 FRANCS SEMEUSE", None, set()),
        ("FRANCE-1855BB-10 Francs 5 plus bas  G. 1014 TBTTB", "BB", {"1014"}),
    ],
)
def test_listing_parsing(name, mint, refs):
    assert listing.listing_mint(name) == mint
    assert listing.listing_refs(name) == refs


def test_reference_match_without_visual_index(catalog_1851):
    m = matching.find(main.catalog_db, make_coin(), [b""], None)
    assert m.row["id"] in catalog_1851 and {r["id"] for r in m.same} == set(catalog_1851)


def test_other_mint_is_not_the_same_coin(catalog_1851):
    assert matching.find(main.catalog_db, make_coin(mint_mark="BB"), [b""], None) is None


def test_facts_without_reference_need_visual_confirmation(catalog_1851):
    coin = make_coin(catalog_refs=[])
    assert matching.find(main.catalog_db, coin, [b""], None) is None  # facts alone are not enough
    a, b = catalog_1851
    m = matching.find(main.catalog_db, coin, [b""], FakeIndex({a: 0.9, b: 0.88}))
    assert m.row["id"] == a and m.similarity == 0.9 and len(m.same) == 2
    assert matching.find(main.catalog_db, coin, [b""], FakeIndex({a: 0.5, b: 0.4})) is None  # looks different


def test_visual_outlier_is_not_counted_as_the_same_type(catalog_1851):
    a, b = catalog_1851
    m = matching.find(main.catalog_db, make_coin(), [b""], FakeIndex({a: 0.92, b: 0.70}))
    assert [r["id"] for r in m.same] == [a]


@pytest.mark.parametrize(
    "face,denomination,expected",
    [
        (0.2, "20 Centimes", [0.2, 20.0]),  # the catalog stores sub-units either way
        (10, "10 Francs", [10]),
        (None, "5 Lire", [5.0]),
        (0.5, "10 Soldi", [0.5, 10.0]),
        (None, None, []),
    ],
)
def test_face_values_cover_sub_units(face, denomination, expected):
    assert matching.face_values(make_coin(face_value=face, denomination=denomination)) == expected


@pytest.mark.parametrize(
    ("read", "year", "rank"),
    [(1861, 1851, 0), (1861, 1867, 5), (1861, 1871, None), (1861, 1851 + 10, None), (1861, 1751, None)],
)
def test_misread_rank(read, year, rank):
    assert years.misread_rank(read, year) == rank


def test_visual_search_looks_at_the_coin_not_the_room():
    from PIL import Image, ImageDraw

    from app import visual

    photo = Image.new("RGB", (900, 1200), (235, 235, 230))  # a holder, the coin low and to the left
    ImageDraw.Draw(photo).ellipse((150, 600, 550, 1000), fill=(200, 160, 60), outline=(90, 60, 20), width=6)
    crop = visual.coin_square(photo)
    assert abs(crop.width - 420) < 30 and abs(crop.height - 420) < 30  # the coin (radius 200) and a 5% margin
