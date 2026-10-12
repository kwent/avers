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
