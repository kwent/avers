"""What a catalog listing says about itself in its wording: the mint letter and the Gadoury numbers. Parsed once,
when a listing is stored (db.upsert_coin), into the `mint`, `gadoury` and `gadoury_all` columns. Plain code."""

import re
import unicodedata

# "FRANCE-1851A-10 Francs …", "FRANCE-1717 W-Ecu …", "FRANCE-1854-A-10 FRANCS …", "HONGRIE-1911 KB-10 Korona …"
LISTING_DATE = re.compile(r"-(\d{4})(?:/\d+)?(?:\s*-?\s*([A-Z]{1,2}))?(?=\s*-)")
GADOURY_REF = re.compile(r"\bG(?:ad(?:oury)?)?\.?\s*(?:[A-Z]{2}\s*)?(\d+[a-z]?)\b", re.I)  # "G. 1012", "Gad FR 1012"


def plain(text: str | None) -> str:
    """Lower case without accents, for loose name matching ("CÉRÉS" ~ "Cérès")."""
    return "".join(c for c in unicodedata.normalize("NFD", (text or "").lower()) if not unicodedata.combining(c))


def listing_mint(name: str | None) -> str | None:
    m = LISTING_DATE.search(name or "")
    return m.group(2) if m else None


def listing_refs(text: str | None) -> set[str]:
    """Gadoury numbers quoted in a listing's text, e.g. 'FRANCE-1851A-10 Francs G. 1012 TTBSUP' -> {'1012'}."""
    return {x.lower() for x in GADOURY_REF.findall(text or "")}


def gadoury_refs(refs: list[str]) -> set[str]:
    """Gadoury numbers among a reading's catalog references ("G. 1012", "KM 770", ...)."""
    out = set()
    for ref in refs:
        m = GADOURY_REF.match(ref.strip())
        if m:
            out.add(m.group(1).lower())
    return out


def facts(name: str | None, description: str | None) -> dict:
    """The parsed columns of a listing. `gadoury`: numbers in the name (what matching trusts); `gadoury_all`: also
    those in the description, which are looser ("G.60" may be a face value), for comparable listings only."""
    return {
        "mint": listing_mint(name),
        "gadoury": _stored(listing_refs(name)),
        "gadoury_all": _stored(listing_refs(name) | listing_refs(description)),
    }


def _stored(refs: set[str]) -> str:
    return f" {' '.join(sorted(refs))} " if refs else ""  # padded, so SQL can match '% 1012 %'


def stored_refs(value: str | None) -> set[str]:
    return set((value or "").split())
