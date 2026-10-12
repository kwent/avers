"""Benchmark vision models on coin reading, through the Vercel AI Gateway (OpenAI-compatible API).

Every model gets the production prompt and schema (app.identify) on:
- catalog coins of known identity (two catalog photos each, sampled per country),
- real phone photos of a known coin (in order, then swapped),
- traps: the same photo blurred beyond reading, and a photo that is not a coin.

Scores: status, country, year, face value, mint, and whether the reading would select the right catalog listing
(app.matching.candidates) — the metric that matters for pricing. Also cost per call and latency.

Run from backend/ (needs data/coins.sqlite, its images, and the e2e fixtures):
    AI_GATEWAY_API_KEY=... uv run python -m bench.models [model ...]
Raw results: data/bench/models-<timestamp>.json (git-ignored).
"""

import base64
import io
import json
import os
import random
import sqlite3
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageFilter

from app import identify, matching
from app.db import DB_PATH, IMAGES_DIR

GATEWAY = "https://ai-gateway.vercel.sh/v1"
FIXTURES = Path(__file__).resolve().parents[2] / "mobile/.maestro/fixtures"
OUT_DIR = DB_PATH.parent / "bench"
PHONE_COIN_ID = 13675  # catalog listing of the coin in the phone fixtures (10 Francs Cérès 1851 A)
PER_COUNTRY = {"FR": 10, "IT": 4, "US": 2, "GB": 2, "VA": 1, "MC": 1, "ES": 1, "DE": 1, "RU": 1, "AT": 1}
SEED = 7
WORKERS = 6

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

SSL = ssl.create_default_context(cafile="/etc/ssl/cert.pem" if Path("/etc/ssl/cert.pem").exists() else None)


def _get(url: str, body: dict | None = None, timeout: int = 180) -> dict:
    headers = {"Authorization": f"Bearer {os.environ['AI_GATEWAY_API_KEY']}", "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout, context=SSL) as resp:
        return json.load(resp)


def prices() -> dict[str, tuple[float, float]]:
    """model id -> (USD per input token, USD per output token)."""
    out = {}
    for m in _get(f"{GATEWAY}/models")["data"]:
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


def cases(db: sqlite3.Connection) -> list[dict]:
    out = []
    rnd = random.Random(SEED)
    for iso, n in PER_COUNTRY.items():
        rows = db.execute(
            "SELECT c.* FROM coins c WHERE country_iso = ? AND year IS NOT NULL AND face_value IS NOT NULL "
            "AND price > 0 AND (SELECT count(*) FROM coin_images i WHERE i.coin_id = c.id "
            "AND i.local_path IS NOT NULL) >= 2",
            (iso,),
        ).fetchall()
        for r in rnd.sample(rows, min(n, len(rows))):
            paths = db.execute(
                "SELECT local_path FROM coin_images WHERE coin_id = ? AND local_path IS NOT NULL "
                "ORDER BY position LIMIT 2",
                (r["id"],),
            ).fetchall()
            imgs = [_jpeg(Image.open(IMAGES_DIR / p[0])) for p in paths]
            out.append({"name": f"catalog-{r['id']}", "imgs": imgs, "truth": dict(r), "expect": "identified"})

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


def _strict_schema() -> dict:
    schema = identify.CoinIdentification.model_json_schema()

    def fix(node):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"])
            for v in node.values():
                fix(v)
        elif isinstance(node, list):
            for v in node:
                fix(v)

    fix(schema)
    return schema


SCHEMA = _strict_schema()


def read_coin(model: str, imgs: list[bytes]) -> tuple[identify.CoinIdentification, float, dict]:
    content = []
    labels = ["Photo 1 (meant to be the obverse)", "Photo 2 (meant to be the reverse)"]
    for label, data in zip(labels, imgs, strict=False):
        url = "data:image/jpeg;base64," + base64.b64encode(data).decode()
        content += [{"type": "text", "text": label}, {"type": "image_url", "image_url": {"url": url}}]
    content.append({"type": "text", "text": "What is this? Identify the coin only if you really can."})
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": identify.IDENTIFY_PROMPT.format(language="French")},
            {"role": "user", "content": content},
        ],
        "response_format": {"type": "json_schema", "json_schema": {"name": "coin", "schema": SCHEMA, "strict": True}},
        "max_tokens": 8000,
    }
    t = time.monotonic()
    resp = _get(f"{GATEWAY}/chat/completions", body)
    elapsed = time.monotonic() - t
    text = resp["choices"][0]["message"]["content"].strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json")
    coin = identify.enforce_confidence(identify.CoinIdentification.model_validate_json(text))
    return coin, elapsed, resp.get("usage") or {}


_db_lock = threading.Lock()


def score(case: dict, coin: identify.CoinIdentification, db: sqlite3.Connection) -> dict:
    out = {"status_ok": coin.status == case["expect"]}
    truth = case["truth"]
    if case["expect"] != "identified" or not truth:
        return out
    out["country"] = (coin.country_iso or "").upper() == truth["country_iso"]
    out["year"] = coin.year == truth["year"]
    out["face"] = coin.face_value is not None and abs(coin.face_value - truth["face_value"]) < 1e-6
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
        err = ""
        for _ in range(2):
            try:
                coin, elapsed, usage = read_coin(model, case["imgs"])
            except urllib.error.HTTPError as e:
                err = f"HTTP {e.code}: {e.read().decode()[:300]}"
                continue
            except Exception as e:  # malformed output, timeout...
                err = f"{type(e).__name__}: {str(e)[:300]}"
                continue
            cost = usage.get("prompt_tokens", 0) * price[0] + usage.get("completion_tokens", 0) * price[1]
            return {
                "case": case["name"],
                "seconds": elapsed,
                "cost": cost,
                "coin": coin.model_dump(),
                **score(case, coin, db),
            }
        return {"case": case["name"], "error": err}

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
    print(f"{len(all_cases)} cases -> {out}")
    results = {}
    for model in models:
        rows = run(model, all_cases, db, table.get(model, (0.0, 0.0)))
        results[model] = rows
        out.write_text(json.dumps(results, indent=1, default=str))
        print(summary(model, rows), flush=True)


if __name__ == "__main__":
    main()
