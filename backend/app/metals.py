"""Spot prices, FX conversion and melt value."""

import threading
import time

from app.http import get_json

TROY_OZ_G = 31.1034768
SPOT_TTL = 300  # seconds
FX_TTL = 3600

# metal -> gold-api.com symbol (prices in USD per troy ounce)
SPOT_SYMBOLS = {"gold": "XAU", "silver": "XAG", "platinum": "XPT", "palladium": "XPD"}

# Gadoury wording -> normalized metal (used to search the catalog and to price melt)
CATALOG_METALS = {
    "gold": ["Or", "Or nordique"],
    "silver": ["Argent", "Billon"],
    "platinum": ["Platine"],
    "copper": ["Cuivre", "Cuivre jaune", "Bronze"],
    "bronze": ["Bronze", "Cuivre"],
    "nickel": ["Nickel", "Cupro-Nickel", "Maillechort"],
    "billon": ["Billon", "Argent"],
    "aluminium": ["Aluminium", "Cupro-aluminium", "Cupro-nickel-alu."],
    "steel": ["Acier Inoxydable"],
    "zinc": ["Zinc"],
}

_lock = threading.Lock()
_cache: dict[str, tuple[float, object]] = {}


def _cached(key: str, ttl: int, fetch):
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
    try:
        value = fetch()
    except Exception:
        if hit:  # serve stale data rather than failing the whole estimate
            return hit[1]
        raise
    with _lock:
        _cache[key] = (time.time(), value)
    return value


def usd_rates() -> dict[str, float]:
    """1 USD -> X currency, for every currency the ECB publishes."""

    def fetch():
        rates = get_json("https://api.frankfurter.dev/v1/latest?base=USD")["rates"]
        return {"USD": 1.0, **rates}

    return _cached("fx", FX_TTL, fetch)


def convert(amount: float | None, src: str, dst: str) -> float | None:
    if amount is None or src == dst:
        return amount
    rates = usd_rates()
    return amount / rates[src] * rates[dst]


def spot_usd_per_oz(metal: str) -> float | None:
    symbol = SPOT_SYMBOLS.get(metal)
    if not symbol:
        return None
    return _cached(
        f"spot:{symbol}", SPOT_TTL, lambda: float(get_json(f"https://api.gold-api.com/price/{symbol}")["price"])
    )


def spot_prices(currency: str) -> dict:
    out = {}
    for metal in SPOT_SYMBOLS:
        usd = spot_usd_per_oz(metal)
        out[metal] = {
            "per_oz": round(convert(usd, "USD", currency), 2),
            "per_gram": round(convert(usd / TROY_OZ_G, "USD", currency), 4),
        }
    return {"currency": currency, "metals": out}


def melt_value(metal: str | None, weight_g: float | None, fineness: float | None, currency: str) -> dict | None:
    """Value of the precious metal content; None when the metal has no meaningful spot price."""
    if not metal or not weight_g or not fineness:
        return None
    if metal == "billon":
        metal = "silver"
    usd = spot_usd_per_oz(metal)
    if usd is None:
        return None
    pure_g = weight_g * fineness
    return {
        "metal": metal,
        "weight_g": weight_g,
        "fineness": fineness,
        "pure_metal_g": round(pure_g, 3),
        "spot_per_gram": round(convert(usd / TROY_OZ_G, "USD", currency), 4),
        "value": round(convert(pure_g * usd / TROY_OZ_G, "USD", currency), 2),
        "currency": currency,
    }
