"""Numista (https://en.numista.com) as a second reference: which years and mints a coin type was really struck in,
its mintage, and an indicative price when the Gadoury catalog has no listing. Optional and best-effort: without
NUMISTA_API_KEY, over quota, or when Numista fails, every function returns None and estimates work as before.

Free plan: 2000 requests a month. Answers are cached in the collection store, so a coin type is fetched once.
"""

import json
import logging
import os
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta

from app.http import SSL_CTX, UA
from app.identify import CoinIdentification

log = logging.getLogger(__name__)

API = "https://api.numista.com/v3"
KEY = os.environ.get("NUMISTA_API_KEY", "")
MAX_PER_MONTH = int(os.environ.get("NUMISTA_MAX_PER_MONTH", "1800"))  # stay under the free plan's 2000
TIMEOUT = 6.0
FACTS_AGE = timedelta(days=180)  # types, issues, catalogues barely change
PRICE_AGE = timedelta(days=30)

# Our French grade scale -> Numista's
GRADES = {"B": "g", "TB": "f", "TTB": "vf", "SUP": "xf", "SPL": "au", "FDC": "unc"}
GRADES_BACK = {v: k for k, v in GRADES.items()} | {"vg": "B"}


def enabled() -> bool:
    return bool(KEY)


def _get(store, path: str, params: dict, max_age: timedelta) -> dict | list | None:
    """GET a Numista endpoint through the cache. None when disabled, over quota or failing."""
    if not KEY:
        return None
    key = f"numista:{path}?{json.dumps(params, sort_keys=True)}"
    hit = store.cached(key, max_age)
    if hit is not None:
        return json.loads(hit)
    if store.bump(f"numista:{datetime.now(UTC):%Y-%m}") > MAX_PER_MONTH:
        log.warning("numista monthly quota reached")
        return None
    url = f"{API}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    req = urllib.request.Request(url, headers={"Numista-API-Key": KEY, "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=SSL_CTX) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code != 404:  # 404 is an answer (no such type/issue); anything else is a failure
            log.warning("numista %s -> %s", path, e.code)
            return None
        data = None
    except (OSError, ValueError) as e:
        log.warning("numista %s failed: %s", path, e)
        return None
    store.cache(key, json.dumps(data))
    return data


def _plain(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (text or "").lower()) if not unicodedata.combining(c))


def _gadoury_catalogue(store) -> int | None:
    """Numista's ID for Gadoury "Monnaies françaises" (not his colonial, necessity or Olympic catalogues)."""
    data = _get(store, "/catalogues", {}, FACTS_AGE) or {}
    for c in data.get("catalogues", []):
        if "gadoury" in _plain(c.get("author", "")) and _plain(c.get("title", "")).startswith("monnaies francaises"):
            return c["id"]
    return None


def _issuer(store, country_name: str | None) -> str | None:
    """Numista's issuer code for a country named in French ("France" -> "france", "Italie" -> "italy")."""
    if not country_name:
        return None
    data = _get(store, "/issuers", {"lang": "fr"}, FACTS_AGE) or {}
    name = _plain(country_name)
    return next((i["code"] for i in data.get("issuers", []) if _plain(i.get("name", "")) == name), None)


def find_type(store, coin: CoinIdentification) -> dict | None:
    """The Numista type of a coin read from photos: by Gadoury number when the reading has one, else by text
    (denomination + type name, same country and face value). A misread year may fall outside the type's years, so
    the year only ranks the candidates."""
    refs = [m.group(1) for r in coin.catalog_refs if (m := re.search(r"\bG(?:ad(?:oury)?)?\.?\s*(\d+[a-z]?)", r, re.I))]
    catalogue = _gadoury_catalogue(store) if refs else None
    found = []
    if catalogue:
        for ref in refs:
            data = _get(store, "/types", {"catalogue": catalogue, "number": ref, "category": "coin"}, FACTS_AGE)
            found += (data or {}).get("types", [])
    if not found:
        words = " ".join(w for w in (coin.denomination, coin.type_name) if w)
        if not words:
            return None
        params = {"q": words, "category": "coin", "count": 20, "lang": "fr"}
        issuer = _issuer(store, coin.country_name)
        if issuer:
            params["issuer"] = issuer
        data = _get(store, "/types", params, FACTS_AGE)
        face = _plain(coin.denomination or "")
        # "20 Francs" must not match "20 centimes": the title has to name the same denomination
        found = [t for t in (data or {}).get("types", []) if not face or face in _plain(t.get("title", ""))]
    if not found:
        return None

    def distance(t: dict) -> int:
        lo, hi = t.get("min_year") or 0, t.get("max_year") or 9999
        return 0 if not coin.year or lo <= coin.year <= hi else min(abs(coin.year - lo), abs(coin.year - hi))

    return min(found, key=distance)  # stable: Numista's relevance order breaks ties


def issues(store, type_id: int) -> list[dict]:
    """Every issue (year, mint letter, mintage) of a type."""
    data = _get(store, f"/types/{type_id}/issues", {}, FACTS_AGE)
    return data if isinstance(data, list) else []


def issue_for(found: list[dict], year: int | None, mint: str | None) -> dict | None:
    same_year = [i for i in found if year and (i.get("gregorian_year") or i.get("year")) == year]
    if mint:
        same_mint = [i for i in same_year if (i.get("mint_letter") or "").upper() == mint.strip().upper()]
        if same_mint:
            return same_mint[0]
    return same_year[0] if same_year else None


def prices(store, type_id: int, issue_id: int, currency: str) -> dict[str, float]:
    """Numista's price estimate per grade, keyed by our grade codes (TB, TTB, ...)."""
    data = _get(store, f"/types/{type_id}/issues/{issue_id}/prices", {"currency": currency}, PRICE_AGE) or {}
    if data.get("currency", currency) != currency:
        return {}
    return {GRADES_BACK[p["grade"]]: p["price"] for p in data.get("prices", []) if p.get("grade") in GRADES_BACK}


def lookup(store, coin: CoinIdentification, currency: str) -> dict | None:
    """What Numista knows about this coin: type, issue (if that year/mint exists), years struck, prices."""
    t = find_type(store, coin)
    if not t:
        return None
    found = issues(store, t["id"])
    issue = issue_for(found, coin.year, coin.mint_mark)
    years = sorted({y for i in found if (y := i.get("gregorian_year") or i.get("year"))})
    return {
        "type_id": t["id"],
        "title": t.get("title"),
        "url": f"https://fr.numista.com/catalogue/pieces{t['id']}.html",
        "years": years,
        "issue": issue and {"id": issue["id"], "mintage": issue.get("mintage"), "mint": issue.get("mint_letter")},
        "prices": prices(store, t["id"], issue["id"], currency) if issue else {},
    }
