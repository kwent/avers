"""Benchmark vision models on coin reading, through the Vercel AI Gateway.

Every model goes through the production call (app.identify.read: same prompt, schema and parsing) on:
- catalog coins of known identity (two catalog photos each, sampled per country),
- real phone photos of a known coin (in order, then swapped),
- traps: the same photo blurred beyond reading, and a photo that is not a coin.

Scores: status, country, year, face value, mint, and whether the reading would select the right catalog listing
(app.matching.candidates) — the metric that matters for pricing. Also cost per call and latency.

Run from backend/ (needs data/coins.sqlite, its images, and the e2e fixtures):
    AI_GATEWAY_API_KEY=... uv run python -m bench.models [model ...]
Raw results: data/bench/models-<timestamp>.json (git-ignored).
"""

import io
import json
import random
import re
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageFilter

from app import identify, matching
from app.db import DB_PATH, IMAGES_DIR
from app.http import get_json

FIXTURES = Path(__file__).resolve().parents[2] / "mobile/.maestro/fixtures"
OUT_DIR = DB_PATH.parent / "bench"
PHONE_COIN_ID = 13675  # catalog listing of the coin in the phone fixtures (10 Francs Cérès 1851 A)
PER_COUNTRY = {"FR": 16, "IT": 6, "US": 3, "GB": 3, "VA": 2, "MC": 2, "ES": 2, "DE": 2, "RU": 2, "AT": 2}
# catalog items that are not coins: excluded from the coin sample, a few kept as extra "not a coin" traps
NOT_COINS = r"(JETON|M[EÉ]DAILLE|COFFRET|BILLET|BERNHARD)"
NOT_COIN_TRAPS = 3
SEED = 7
WORKERS = 6
RETRIES = 6  # rate limits and transient errors: wait 2, 4, 8... seconds (or Retry-After) between attempts

DEFAULT_MODELS = [
    "anthropic/claude-opus-5.5",
    "anthropic/claude-sonnet-5.5",
    "anthropic/claude-haiku-5.5",
    "google/gemini-3.8-flash",
    "google/gemini-3.5-flash-lite",
    "openai/gpt-6-sol",
    "openai/gpt-6-luna",
    "alibaba/qwen3.8-flash",
]


def prices() -> dict[str, tuple[float, float]]:
    """model id -> (USD per input token, USD per output token)."""
    out = {}
    for m in get_json(f"{identify.GATEWAY_URL}/models")["data"]:
        p = m.get("pricing") or {}
        if p.get("input"):
            out[m["id"]] = (float(p["input"]), float(p.get("output", 0)))
    return out


def _jpeg(img: Image.Image, max_side: int = 1600) -> bytes:
    img = img.convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue()


def _catalog_photos(db: sqlite3.Connection, coin_id: int) -> list[bytes]:
    paths = db.execute(
        "SELECT local_path FROM coin_images WHERE coin_id = ? AND local_path IS NOT NULL ORDER BY position LIMIT 2",
        (coin_id,),
    ).fetchall()
    return [_jpeg(Image.open(IMAGES_DIR / p[0])) for p in paths]


def cases(db: sqlite3.Connection) -> list[dict]:
    out = []
    rnd = random.Random(SEED)
    with_photos = (
        "price > 0 AND (SELECT count(*) FROM coin_images i WHERE i.coin_id = c.id AND i.local_path IS NOT NULL) >= 2"
    )
    for iso, n in PER_COUNTRY.items():
        rows = db.execute(
            f"SELECT c.* FROM coins c WHERE country_iso = ? AND year IS NOT NULL AND face_value > 0 AND {with_photos}",
            (iso,),
        ).fetchall()
        rows = [r for r in rows if not re.search(NOT_COINS, r["name"], re.I)]
        for r in rnd.sample(rows, min(n, len(rows))):
            out.append(
                {
                    "name": f"catalog-{r['id']}",
                    "imgs": _catalog_photos(db, r["id"]),
                    "truth": dict(r),
                    "expect": "identified",
                }
            )
    others = [
        r for r in db.execute(f"SELECT c.* FROM coins c WHERE {with_photos}") if re.search(NOT_COINS, r["name"], re.I)
    ]
    for r in rnd.sample(others, min(NOT_COIN_TRAPS, len(others))):
        out.append(
            {"name": f"trap-{r['id']}", "imgs": _catalog_photos(db, r["id"]), "truth": None, "expect": "not_a_coin"}
        )

    front, back = (FIXTURES / "coin-front.jpg").read_bytes(), (FIXTURES / "coin-back.jpg").read_bytes()
    truth = dict(db.execute("SELECT * FROM coins WHERE id = ?", (PHONE_COIN_ID,)).fetchone())
    blurred = _jpeg(Image.open(io.BytesIO(front)).filter(ImageFilter.GaussianBlur(25)))
    out += [
        {"name": "phone", "imgs": [front, back], "truth": truth, "expect": "identified"},
        {"name": "phone-swapped", "imgs": [back, front], "truth": truth, "expect": "identified", "swapped": True},
        {"name": "blurred", "imgs": [blurred], "truth": None, "expect": "unidentifiable"},
        {
            "name": "not-a-coin",
            "imgs": [(FIXTURES / "not-coin.jpg").read_bytes()],
            "truth": None,
            "expect": "not_a_coin",
        },
    ]
    return out


def read_coin(model: str, imgs: list[bytes]) -> tuple[identify.CoinIdentification, float, dict]:
    """Production call, retried on rate limits and transient errors with exponential backoff."""
    for attempt in range(RETRIES):
        t = time.monotonic()
        try:
            coin, resp = identify.read([(data, "image/jpeg") for data in imgs], "fr", model=model)
            return coin, time.monotonic() - t, resp.get("usage") or {}
        except identify.VisionError as e:
            transient = e.status is None or e.status == 429 or e.status >= 500
            if not transient or attempt == RETRIES - 1:
                raise
            wait = e.retry_after or 2 ** (attempt + 1)
            print(f"  {model}: {e.status or 'network'} error, retry in {wait:.0f}s", flush=True)
            time.sleep(min(wait, 60) * random.uniform(1, 1.5))
    raise AssertionError("unreachable")


_db_lock = threading.Lock()


def score(case: dict, coin: identify.CoinIdentification, db: sqlite3.Connection) -> dict:
    out = {"status_ok": coin.status == case["expect"]}
    truth = case["truth"]
    if case["expect"] != "identified" or not truth:
        return out
    out["country"] = (coin.country_iso or "").upper() == truth["country_iso"]
    out["year"] = coin.year == truth["year"]
    out["face"] = truth["face_value"] in matching.face_values(coin)
    mint = matching.listing_mint(truth["name"])
    out["mint"] = None if not mint else (coin.mint_mark or "").strip().upper() == mint
    out["candidate"] = False
    if coin.status == "identified":
        with _db_lock:
            rows, _ = matching.candidates(db, coin)
        out["candidate"] = truth["id"] in {r["id"] for r in rows}
    if case.get("swapped"):
        out["sides"] = coin.photo_sides[:2] == ["reverse", "obverse"]
    return out


def run(model: str, all_cases: list[dict], db: sqlite3.Connection, price: tuple[float, float]) -> list[dict]:
    def one(case):
        try:
            coin, elapsed, usage = read_coin(model, case["imgs"])
        except identify.VisionError as e:
            print(f"  {model} {case['name']}: ERROR {str(e)[:120]}", flush=True)
            return {"case": case["name"], "error": str(e)}
        cost = usage.get("prompt_tokens", 0) * price[0] + usage.get("completion_tokens", 0) * price[1]
        row = {
            "case": case["name"],
            "seconds": elapsed,
            "cost": cost,
            "coin": coin.model_dump(),
            **score(case, coin, db),
        }
        verdict = row.get("candidate", row["status_ok"])
        print(f"  {model} {case['name']}: {'ok' if verdict else 'miss'} ({coin.status}, {elapsed:.1f}s)", flush=True)
        return row

    with ThreadPoolExecutor(WORKERS) as ex:
        return list(ex.map(one, all_cases))


def summary(model: str, rows: list[dict]) -> str:
    ok = [r for r in rows if "error" not in r]
    coins = [r for r in ok if r["case"].startswith(("catalog-", "phone"))]

    def frac(key):
        vals = [r[key] for r in coins if r.get(key) is not None]
        return f"{sum(vals)}/{len(vals)}" if vals else "-"

    traps = " ".join(
        f"{r['case']}:{'ok' if r['status_ok'] else 'FAIL'}"
        for r in ok
        if not r["case"].startswith(("catalog-", "phone"))
    )
    cost = sum(r["cost"] for r in ok) / max(len(ok), 1)
    p50 = sorted(r["seconds"] for r in ok)[len(ok) // 2] if ok else 0
    return (
        f"{model:30} errors {len(rows) - len(ok):2} | identified {frac('status_ok')} country {frac('country')} "
        f"year {frac('year')} face {frac('face')} mint {frac('mint')} -> catalog {frac('candidate')} | "
        f"swap {frac('sides')} | {traps} | ${cost:.4f}/call p50 {p50:.1f}s"
    )


def main() -> None:
    models = sys.argv[1:] or DEFAULT_MODELS
    db = sqlite3.connect(DB_PATH, check_same_thread=False)
    db.row_factory = sqlite3.Row
    all_cases = cases(db)
    table = prices()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"models-{time.strftime('%Y%m%d-%H%M%S')}.json"
    print(f"{len(all_cases)} cases -> {out}", flush=True)
    results = {}
    for model in models:
        rows = run(model, all_cases, db, table.get(model, (0.0, 0.0)))
        results[model] = rows
        out.write_text(json.dumps(results, indent=1, default=str))
        print(summary(model, rows), flush=True)


if __name__ == "__main__":
    main()
