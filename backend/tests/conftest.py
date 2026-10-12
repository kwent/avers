import os
import sys
import tempfile
from pathlib import Path

# Point every data path at a throwaway directory before the app modules are imported.
_tmp = Path(tempfile.mkdtemp(prefix="avers-test-"))
os.environ["COINS_DB"] = str(_tmp / "coins.sqlite")
os.environ["COINS_IMAGES"] = str(_tmp / "images")
os.environ["COLLECTION_DB"] = str(_tmp / "collection.sqlite")
os.environ["UPLOADS_DIR"] = str(_tmp / "uploads")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app import metals  # noqa: E402

SPOT_USD = {"gold": 4000.0, "silver": 50.0, "platinum": 1500.0, "palladium": 1000.0}
RATES = {"USD": 1.0, "EUR": 0.9, "CHF": 0.8}


@pytest.fixture(autouse=True)
def offline_prices(monkeypatch):
    """No network in tests: fixed spot prices and FX rates."""
    monkeypatch.setattr(metals, "spot_usd_per_oz", lambda metal: SPOT_USD.get(metal))
    monkeypatch.setattr(metals, "usd_rates", lambda: RATES)


@pytest.fixture
def catalog_1851():
    """Listings of the 10 Francs Cérès 1851 A in the shared test catalog (TTB 600 €, SUP 1000 €), removed after."""
    from datetime import date

    from app import main
    from app.db import upsert_coin

    db = main.catalog_db
    ids = []
    for sid, grade, price in (("p1", "TTB", 600), ("p2", "SUP", 1000)):
        ids.append(
            upsert_coin(
                db,
                {
                    "source": "test",
                    "source_id": sid,
                    "name": f"FRANCE-1851A-10 Francs 2e République G. 1012 {grade}",
                    "url": f"https://example.com/{sid}",
                    "country_iso": "FR",
                    "year": 1851,
                    "face_value": 10,
                    "metal": "Or",
                    "weight_g": 3.22,
                    "grade": grade,
                    "price": price,
                    "currency": "EUR",
                    "in_stock": 1,
                    "modified": f"{date.today().year}-01-01",
                },
                [],
            )
        )
    db.commit()
    yield ids
    db.execute(f"DELETE FROM coins WHERE id IN ({','.join('?' * len(ids))})", ids)
    db.commit()
