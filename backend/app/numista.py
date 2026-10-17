"""Numista (https://en.numista.com) as a second reference: which years and mints a coin type was really struck in,
its mintage, and an indicative price when the Gadoury catalog has no listing. Optional and best-effort: without
NUMISTA_API_KEY, over quota, or when Numista fails, every function returns None and estimates work as before.

Free plan: 2000 requests a month. Answers are cached in the collection store, so a coin type is fetched once.
"""

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta

from app.http import SSL_CTX, UA
from app.identify import CoinIdentification
from app.listing import gadoury_refs, plain
from app.matching import type_words

log = logging.getLogger(__name__)

API = "https://api.numista.com/v3"
KEY = os.environ.get("NUMISTA_API_KEY", "")
MAX_PER_MONTH = int(os.environ.get("NUMISTA_MAX_PER_MONTH", "1800"))  # stay under the free plan's 2000
TIMEOUT = 6.0
FACTS_AGE = timedelta(days=180)  # types, issues, catalogues barely change
PRICE_AGE = timedelta(days=30)
GENERIC_TYPE_WORDS = {"republique", "empire", "royaume", "regne", "type", "serie", "armoiries", "embleme"}
MAX_TIED = 4  # types sharing the year read whose issues are compared (one request each, cached)

# Our French grade scale -> Numista's
GRADES = {"B": "g", "TB": "f", "TTB": "vf", "SUP": "xf", "SPL": "au", "FDC": "unc"}
GRADES_BACK = {v: k for k, v in GRADES.items()} | {"vg": "B"}


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


_lists: dict[str, tuple[datetime, dict]] = {}


def _list(store, path: str, params: dict) -> dict:
    """A whole Numista list (catalogues, issuers): parsed once per instance, not on every estimate."""
    hit = _lists.get(path)
    if hit and datetime.now(UTC) - hit[0] < FACTS_AGE:
        return hit[1]
    data = _get(store, path, params, FACTS_AGE)
    if data:
        _lists[path] = (datetime.now(UTC), data)
    return data or {}


def _gadoury_catalogue(store) -> int | None:
    """Numista's ID for Gadoury "Monnaies françaises" (not his colonial, necessity or Olympic catalogues)."""
    data = _list(store, "/catalogues", {})
    for c in data.get("catalogues", []):
        if "gadoury" in plain(c.get("author", "")) and plain(c.get("title", "")).startswith("monnaies francaises"):
            return c["id"]
    return None


def _issuer(store, country_name: str | None) -> str | None:
    """Numista's issuer code for a country named in French ("France" -> "france", "Italie" -> "italy")."""
    if not country_name:
        return None
    data = _list(store, "/issuers", {"lang": "fr"})
    name = plain(country_name)
    return next((i["code"] for i in data.get("issuers", []) if plain(i.get("name", "")) == name), None)


def find_type(store, coin: CoinIdentification) -> dict | None:
    """The Numista type of a coin read from photos: by Gadoury number when the reading has one, else by text
    (denomination + type name, same country and face value). A misread year may fall outside the type's years, so
    the year only ranks the candidates."""
    refs = sorted(gadoury_refs(coin.catalog_refs))
    catalogue = _gadoury_catalogue(store) if refs else None
    face = _singular(coin.denomination)

    def same_face(t: dict) -> bool:  # "20 Francs" must not match "20 centimes": the title names the denomination
        return not face or face in _singular(t.get("title"))

    # words naming the type: "Cérès (IIIe République)" -> ["ceres"]; the regime in brackets and words every
    # type shares ("République", "Empire") would make "1 centime Dupré (IIe république)" a match
    bare = coin.model_copy(update={"type_name": re.sub(r"\(.*?\)", " ", coin.type_name or "")})
    words = [w for w in type_words(bare) if w not in GENERIC_TYPE_WORDS]

    def named(t: dict) -> bool:  # the title names the type read ("1 centime Cérès"), or there is nothing to name
        return not words or any(w in plain(t.get("title")) for w in words)

    found = []
    if catalogue:
        for ref in refs:
            data = _get(store, "/types", {"catalogue": catalogue, "number": ref, "category": "coin"}, FACTS_AGE)
            # a reading can quote a wrong number (G. 476 is the 1 Franc de Gaulle, not a 40 Francs Louis XVIII)
            found += [t for t in (data or {}).get("types", []) if same_face(t)]
    by_number = {t["id"] for t in found}
    # The reading's type name is free text in the UI language ("Femme en costume traditionnel"): Numista matches
    # every word, so search the denomination alone (and in the singular: "10 Schillings") when the phrase finds
    # nothing. A Gadoury number is often misquoted: unless it gave a type of that name (not a pattern), the text
    # search runs too ("1 centime Cérès" quoted as G. 78, the 1 centime Dupré).
    phrase = " ".join(w for w in (coin.denomination, coin.type_name) if w)
    named_phrase = " ".join([coin.denomination or "", *words]).strip()  # "1 Centime ceres"
    for query in dict.fromkeys([phrase, named_phrase, coin.denomination or "", face]):
        if any(not _pattern(t) and (named(t) or t["id"] not in by_number) for t in found) or not query:
            break
        params = {"q": query, "category": "coin", "count": 20, "lang": "fr"}
        issuer = _issuer(store, coin.country_name)
        if issuer:
            params["issuer"] = issuer
        data = _get(store, "/types", params, FACTS_AGE)
        found += [t for t in (data or {}).get("types", []) if same_face(t)]
    if not found:
        return None

    def rank(t: dict) -> tuple[int, bool, bool]:  # years away from the year read, then patterns, then other names
        lo, hi = t.get("min_year") or 0, t.get("max_year") or 9999
        years = 0 if not coin.year or lo <= coin.year <= hi else min(abs(coin.year - lo), abs(coin.year - hi))
        return years, _pattern(t), not named(t)

    best = min(map(rank, found))
    tied = [t for t in found if rank(t) == best]
    if len(tied) == 1 or not coin.year:
        return tied[0]  # Numista's relevance order breaks ties

    def struck(t: dict) -> int:
        """Mintage of the issue this coin would be (0 if none): a type with a real issue for the year and mint
        read beats a same-year pattern or rarity (20 centesimi 1863: 27 million struck at Milan vs a 461-piece
        Turin type)."""
        issue = issue_for(issues(store, t["id"]), coin.year, coin.mint_mark)
        return (issue.get("mintage") or 1) if issue else 0

    return max(tied[:MAX_TIED], key=struck)  # stable: Numista's relevance order breaks ties


def _singular(text: str | None) -> str:
    """Plain text with plural endings dropped, to compare denominations: "10 Schillings" ~ "10 schilling"."""
    return " ".join(w[:-1] if len(w) > 3 and w.endswith("s") else w for w in plain(text).split())


def _pattern(t: dict) -> bool:
    """A pattern, trial or piedfort strike, not a coin that circulated: "1 centime (Épreuve en bronze...)"."""
    return bool(re.search(r"\b(essai|epreuve|pattern|piefort|piedfort|trial)\b", plain(t.get("title"))))


def issues(store, type_id: int) -> list[dict]:
    """Every issue (year, mint letter, mintage) of a type."""
    data = _get(store, f"/types/{type_id}/issues", {}, FACTS_AGE)
    return data if isinstance(data, list) else []


def _mint(letters: str | None) -> str:
    """The mint letter itself, without the mint officials' marks: "M BN" (Milan) -> "M"."""
    return (letters or "").strip().upper().split(" ")[0]


def issue_for(found: list[dict], year: int | None, mint: str | None) -> dict | None:
    """The issue of the year and mint read. The most struck first: the circulation strike, not a proof of the year.
    A mint read that no issue of the year has gets no issue: another mint's can be worth a hundred times more."""
    same_year = [i for i in found if year and (i.get("gregorian_year") or i.get("year")) == year]
    same_year.sort(key=lambda i: i.get("mintage") or 0, reverse=True)
    if mint and any(i.get("mint_letter") for i in same_year):
        return next((i for i in same_year if _mint(i.get("mint_letter")) == _mint(mint)), None)
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
    details = _get(store, f"/types/{t['id']}", {"lang": "fr"}, FACTS_AGE) or {}
    metal, fineness = composition((details.get("composition") or {}).get("text"))
    return {
        "type_id": t["id"],
        "title": t.get("title"),
        "url": f"https://fr.numista.com/catalogue/pieces{t['id']}.html",
        "years": years,
        "issue": issue and {"id": issue["id"], "mintage": issue.get("mintage"), "mint": issue.get("mint_letter")},
        "prices": prices(store, t["id"], issue["id"], currency) if issue else {},
        "weight_g": details.get("weight"),
        # Numista's photos of the type, to compare with the coin in hand (credited as Numista asks)
        "images": [
            {"url": side["picture"], "credit": side.get("picture_copyright")}
            for side in (details.get("obverse"), details.get("reverse"))
            if side and side.get("picture")
        ],
        "metal": metal,
        "fineness": fineness,
    }


# Main metal of a Numista composition (French or English wording) -> our precious metal names
COMPOSITION_METALS = {
    "or": "gold",
    "gold": "gold",
    "argent": "silver",
    "silver": "silver",
    "billon": "billon",
    "platine": "platinum",
    "platinum": "platinum",
    "palladium": "palladium",
}


def composition(text: str | None) -> tuple[str | None, float | None]:
    """Precious metal and fineness of a Numista composition: "Argent 640‰ (Copper .360)" -> ("silver", 0.64).
    (None, None) for base metals or when the fineness is not given."""
    words = plain(text).split()
    metal = COMPOSITION_METALS.get(words[0]) if words else None
    m = re.search(r"(\d{3,4})\s*‰|\.(\d{3})\b", text or "")
    if not metal or not m:
        return None, None
    return metal, int(m.group(1)) / 1000 if m.group(1) else int(m.group(2)) / 1000
