"""Avers API.

Run: uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

import io
import json
import os
import secrets
import uuid

import anthropic
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps
from pydantic import BaseModel

from app import catalog, collection, framecheck, identify, metals
from app.db import IMAGES_DIR, connect

MAX_SIDE = 1568  # Claude downsizes anything larger anyway
APP_TOKEN = os.environ.get("APP_TOKEN")  # optional shared secret once exposed beyond the LAN


def check_token(x_app_token: str | None = Header(default=None)):
    if APP_TOKEN and not (x_app_token and secrets.compare_digest(x_app_token, APP_TOKEN)):
        raise HTTPException(401, "invalid token")


app = FastAPI(title="Avers API", dependencies=[Depends(check_token)])
catalog_db = connect()
collection_db = collection.connect()
app.mount("/uploads", StaticFiles(directory=collection.UPLOADS_DIR), name="uploads")
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/catalog-images", StaticFiles(directory=IMAGES_DIR), name="catalog-images")


def _normalize_photo(upload: UploadFile) -> tuple[bytes, str]:
    """Fix rotation, downsize, re-encode as JPEG; store a copy in uploads. Returns (jpeg bytes, file name)."""
    try:
        img = Image.open(upload.file)
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception as e:
        raise HTTPException(400, f"{upload.filename}: unreadable image") from e
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    name = f"{uuid.uuid4().hex}.jpg"
    (collection.UPLOADS_DIR / name).write_bytes(buf.getvalue())
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
    photos = [_normalize_photo(front)] + ([_normalize_photo(back)] if back else [])
    try:
        coin = identify.identify([(data, "image/jpeg") for data, _ in photos], language)
    except anthropic.APIError as e:
        raise HTTPException(502, f"identification failed: {e}") from e
    except RuntimeError as e:
        raise HTTPException(422, str(e)) from e

    names = [name for _, name in photos]
    photo_warning = None
    if len(names) == 2 and len(coin.photo_sides) == 2:
        if coin.photo_sides == ["reverse", "obverse"]:
            names.reverse()  # the user swapped the sides: show the obverse first
        elif coin.photo_sides[0] == coin.photo_sides[1] != "unclear":
            photo_warning = "same_side"

    result = {
        "currency": currency,
        "language": language,
        "photos": {"front": names[0], "back": names[1] if len(names) > 1 else None},
        "photo_warning": photo_warning,
        "identification": coin.model_dump(),
        "melt": None,
        "comparables": [],
        "valuation": None,
    }
    if coin.status != "identified":
        return result  # never value something we could not identify

    result["already_owned"] = collection.owned_count(collection_db, coin.country_iso, coin.year, coin.denomination)
    result["melt"] = metals.melt_value(coin.metal, coin.weight_g, coin.fineness, currency)
    result["comparables"] = catalog.comparables(catalog_db, coin, currency)
    try:
        result["valuation"] = identify.valuate(
            coin, result["melt"], result["comparables"], currency, language
        ).model_dump()
    except (anthropic.APIError, RuntimeError) as e:
        result["valuation_error"] = str(e)
    return result


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
    item = {k: row[k] for k in row.keys() if k != "estimate"}  # noqa: SIM118 (sqlite3.Row has no __iter__ over keys)
    src = row["value_currency"]
    item["value_low"] = metals.convert(row["value_low"], src, currency)
    item["value_high"] = metals.convert(row["value_high"], src, currency)
    item["value_currency"] = currency
    item["melt"] = metals.melt_value(row["metal"], row["weight_g"], row["fineness"], currency)
    return item


@app.get("/collection")
def list_collection(currency: str = "EUR"):
    currency = currency.upper()
    items = [_item_view(r, currency) for r in collection_db.execute("SELECT * FROM items ORDER BY created_at DESC")]

    def total(key: str) -> float:
        return round(sum((i[key] or 0) * i["quantity"] for i in items), 2)

    return {
        "currency": currency,
        "items": items,
        "totals": {
            "count": sum(i["quantity"] for i in items),
            "value_low": total("value_low"),
            "value_high": total("value_high"),
            "melt": round(sum((i["melt"] or {}).get("value", 0) * i["quantity"] for i in items), 2),
        },
    }


@app.post("/collection")
def add_item(body: NewItem):
    item_id = collection.add(collection_db, body.estimate, body.quantity, body.notes)
    return get_item(item_id, body.estimate.get("currency", "EUR"))


@app.get("/collection/{item_id}")
def get_item(item_id: int, currency: str = "EUR"):
    row = collection_db.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        raise HTTPException(404)
    return {**_item_view(row, currency.upper()), "estimate": json.loads(row["estimate"] or "null")}


@app.patch("/collection/{item_id}")
def patch_item(item_id: int, body: ItemPatch, currency: str = "EUR"):
    collection.update(collection_db, item_id, body.model_dump(exclude_unset=True))
    return get_item(item_id, currency)


@app.delete("/collection/{item_id}")
def delete_item(item_id: int):
    collection_db.execute("DELETE FROM items WHERE id = ?", (item_id,))
    collection_db.commit()
    return {"ok": True}
