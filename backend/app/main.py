"""Avers API.

Run: uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

import io
import json
import os
import secrets
import uuid

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageOps
from pydantic import BaseModel, Field, ValidationError

from app import collection, framecheck, identify, metals, pipeline, visual
from app.db import connect

MAX_SIDE = 1568  # vision models downsize anything larger anyway
APP_TOKEN = os.environ.get("APP_TOKEN")  # optional shared secret once exposed beyond the LAN
# Backstop against abuse of the vision model (a leaked access code): estimates per UTC day, 0 = unlimited.
MAX_ESTIMATES_PER_DAY = int(os.environ.get("MAX_ESTIMATES_PER_DAY", "100"))


def check_token(request: Request, x_app_token: str | None = Header(default=None)):
    if request.method == "OPTIONS" or request.url.path.startswith("/uploads/"):
        return  # image views cannot send headers; photo names are random
    if APP_TOKEN and not (x_app_token and secrets.compare_digest(x_app_token, APP_TOKEN)):
        raise HTTPException(401, "invalid token")


app = FastAPI(title="Avers API", dependencies=[Depends(check_token)])
# The web build of the app is served from another origin (comma-separated list, e.g. https://avers.vercel.app).
if origins := [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]:
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"], max_age=3600)
catalog_db = connect()
# Visual search over catalog photos (optional `vision` extra; built with `python -m app.visual build`)
visual_index = visual.Index(catalog_db) if visual.available() else None
store = collection.connect()


def _normalize_photo(upload: UploadFile) -> tuple[bytes, str]:
    """Fix rotation, downsize, re-encode as JPEG; keep a copy for the collection. Returns (jpeg bytes, photo name)."""
    try:
        img = Image.open(upload.file)
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception as e:
        raise HTTPException(400, f"{upload.filename}: unreadable image") from e
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    name = f"{uuid.uuid4().hex}.jpg"
    store.put_photo(name, buf.getvalue())
    return buf.getvalue(), name


@app.get("/health")
def health():
    n = catalog_db.execute("SELECT COUNT(*) FROM coins").fetchone()[0]
    return {"ok": True, "catalog_coins": n}


@app.get("/spot")
def spot(currency: str = "EUR"):
    return metals.spot_prices(currency.upper())


@app.post("/frame-check")
def frame_check(frame: UploadFile = File(...)):
    """Cheap live-camera guidance: is there a sharp, well-lit, centred coin in the guide circle?"""
    try:
        return framecheck.check_frame(frame.file.read()).to_dict()
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/estimate")
def estimate(
    front: UploadFile = File(...),
    back: UploadFile | None = File(None),
    currency: str = Form("EUR"),
    language: str = Form(identify.DEFAULT_LANGUAGE),
):
    currency = currency.upper()
    language = language if language in identify.LANGUAGES else identify.DEFAULT_LANGUAGE
    if MAX_ESTIMATES_PER_DAY and store.count_estimate() > MAX_ESTIMATES_PER_DAY:
        raise HTTPException(429, "daily estimate limit reached")
    store.prune_photos()
    photos = [_normalize_photo(front)] + ([_normalize_photo(back)] if back else [])
    try:
        return pipeline.run(photos, currency, language, catalog_db, store, visual_index)
    except identify.VisionError as e:
        raise HTTPException(502, f"identification failed: {e}") from e


class YearCorrection(BaseModel):
    estimate: dict
    year: int = Field(ge=1, le=2100)


@app.post("/estimate/year")
def estimate_year(body: YearCorrection):
    """Re-price an estimate with the year the user reads on the coin (no AI call, so not counted in the daily cap)."""
    try:
        return pipeline.correct_year(body.estimate, body.year, catalog_db, store, visual_index)
    except (KeyError, TypeError, ValidationError) as e:
        raise HTTPException(422, "not an estimate") from e


@app.get("/catalog/search")
def catalog_search(q: str = "", country: str | None = None, year: int | None = None, limit: int = 30):
    where, params = ["1"], []
    for word in q.split():
        where.append("name LIKE ?")
        params.append(f"%{word}%")
    if country:
        where.append("country_iso = ?")
        params.append(country.upper())
    if year:
        where.append("year = ?")
        params.append(year)
    rows = catalog_db.execute(
        f"SELECT id, source, name, url, year, grade, metal, weight_g, price, currency, in_stock FROM coins"
        f" WHERE {' AND '.join(where)} ORDER BY in_stock DESC, modified DESC LIMIT ?",
        [*params, min(limit, 100)],
    ).fetchall()
    return [dict(r) for r in rows]


class NewItem(BaseModel):
    estimate: dict
    quantity: int = 1
    notes: str | None = None


class ItemPatch(BaseModel):
    title: str | None = None
    year: int | None = None
    denomination: str | None = None
    grade: str | None = None
    quantity: int | None = None
    value_low: float | None = None
    value_high: float | None = None
    notes: str | None = None


def _item_view(row, currency: str) -> dict:
    item = {k: v for k, v in row.items() if k != "estimate"}
    src = row["value_currency"]
    item["value_low"] = metals.convert(row["value_low"], src, currency)
    item["value_high"] = metals.convert(row["value_high"], src, currency)
    item["value_currency"] = currency
    item["melt"] = metals.melt_value(row["metal"], row["weight_g"], row["fineness"], currency)
    return item


@app.get("/collection")
def list_collection(currency: str = "EUR"):
    currency = currency.upper()
    items = [_item_view(r, currency) for r in store.items()]

    def total(key: str, rows: list[dict]) -> float:
        return round(sum((i[key] or 0) * i["quantity"] for i in rows), 2)

    def melt(rows: list[dict]) -> float:
        return round(sum((i["melt"] or {}).get("value", 0) * i["quantity"] for i in rows), 2)

    priced = [i for i in items if i["value_low"] is not None]
    unpriced = [i for i in items if i["value_low"] is None]
    return {
        "currency": currency,
        "items": items,
        "totals": {
            "count": sum(i["quantity"] for i in items),
            # priced coins at their value, the others at their metal value (the one sure figure)
            "total_low": round(total("value_low", priced) + melt(unpriced), 2),
            "total_high": round(total("value_high", priced) + melt(unpriced), 2),
            "priced_count": sum(i["quantity"] for i in priced),
            "value_low": total("value_low", priced),
            "value_high": total("value_high", priced),
            "unpriced_count": sum(i["quantity"] for i in unpriced),
            "unpriced_melt": melt(unpriced),
            "melt": melt(items),
        },
    }


@app.post("/collection")
def add_item(body: NewItem):
    item_id = store.add(body.estimate, body.quantity, body.notes)
    return get_item(item_id, body.estimate.get("currency", "EUR"))


@app.get("/collection/{item_id}")
def get_item(item_id: int, currency: str = "EUR"):
    row = store.get(item_id)
    if not row:
        raise HTTPException(404)
    return {**_item_view(row, currency.upper()), "estimate": json.loads(row["estimate"] or "null")}


@app.patch("/collection/{item_id}")
def patch_item(item_id: int, body: ItemPatch, currency: str = "EUR"):
    store.update(item_id, body.model_dump(exclude_unset=True))
    return get_item(item_id, currency)


@app.delete("/collection/{item_id}")
def delete_item(item_id: int):
    store.delete(item_id)
    return {"ok": True}


@app.get("/uploads/{name}")
def photo(name: str):
    """Photos of the user's coins (exempt from the app token, see check_token)."""
    data = store.photo(name)
    if data is None:
        raise HTTPException(404)
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=31536000, immutable"})
