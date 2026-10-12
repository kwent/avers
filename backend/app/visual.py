"""Visual search: find catalog coins that look like the user's photos.

Each catalog image gets a DINOv2 embedding (stored in coins.sqlite). A query embeds the user's photos at several
rotations (a coin can be shot at any angle) and ranks catalog coins by their best-matching image.

Serving uses an ONNX export of the model (onnxruntime: small and quick to start, fits a serverless function);
building the index and exporting the model need the `vision` extra (torch + transformers + onnx):

    uv run --extra vision python -m app.visual build     # embed catalog images missing from the index
    uv run --extra vision python -m app.visual export    # write the ONNX model used at serving time

Without the ONNX model file, `available()` is False and matching relies on catalog references alone.
"""

import io
import os
import sqlite3
import sys
import threading
from functools import lru_cache

import numpy as np
from PIL import Image, ImageOps

from app import framecheck
from app.db import BACKEND, IMAGES_DIR, ROOT, connect

MODEL = "facebook/dinov2-small"
ONNX_PATH = BACKEND / os.environ.get("VISION_ONNX", ROOT / "data" / "models" / "dinov2-small.onnx")
ROTATIONS = (0, 45, 90, 135, 180, 225, 270, 315)
DIM = 768  # CLS + mean patch token of dinov2-small (384 each)
BATCH = 64
# DINOv2 preprocessing (transformers BitImageProcessor): shortest edge 256 (bicubic), centre crop 224, ImageNet norm
RESIZE, CROP = 256, 224
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

SCHEMA = """
CREATE TABLE IF NOT EXISTS coin_embeddings (
  coin_id INTEGER NOT NULL REFERENCES coins(id) ON DELETE CASCADE,
  position INTEGER NOT NULL,
  model TEXT NOT NULL,
  vector BLOB NOT NULL,          -- float32, L2-normalised
  PRIMARY KEY (coin_id, position, model)
);
"""


def available() -> bool:
    return ONNX_PATH.exists()


@lru_cache(maxsize=1)
def _session():
    import onnxruntime

    return onnxruntime.InferenceSession(str(ONNX_PATH), providers=["CPUExecutionProvider"])


_lock = threading.Lock()


def square(img: Image.Image) -> Image.Image:
    """Centre square crop, RGB, EXIF-rotated."""
    img = ImageOps.exif_transpose(img).convert("RGB")
    side = min(img.size)
    left, top = (img.width - side) // 2, (img.height - side) // 2
    return img.crop((left, top, left + side, top + side))


COIN_SEARCH_SIDE = 640  # px, where the coin is looked for
COIN_MARGIN = 1.05  # crop a little beyond the coin's edge


def coin_square(img: Image.Image) -> Image.Image:
    """The square around the coin, wherever it is in the photo (a library photo shows the holder, fingers, the
    room): what surrounds the coin would otherwise weigh in the similarity. The centre square when no coin is found."""
    img = ImageOps.exif_transpose(img).convert("RGB")
    k = COIN_SEARCH_SIDE / max(img.size)
    small = img.resize((round(img.width * k), round(img.height * k)))
    side = min(small.size)
    found = framecheck.find_coin(np.asarray(small.convert("L")), side * 0.15, side * 0.5)
    if found is None:
        return square(img)
    x, y, r = (v / k for v in found)
    half = r * COIN_MARGIN
    box = (max(0, x - half), max(0, y - half), min(img.width, x + half), min(img.height, y + half))
    return img.crop(tuple(round(v) for v in box))


def preprocess(images: list[Image.Image]) -> np.ndarray:
    """Images -> (n, 3, 224, 224) float32, as the DINOv2 image processor does."""
    out = []
    for img in images:
        img = img.convert("RGB")
        scale = RESIZE / min(img.size)
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.BICUBIC)
        left, top = (img.width - CROP) // 2, (img.height - CROP) // 2
        img = img.crop((left, top, left + CROP, top + CROP))
        arr = (np.asarray(img, dtype=np.float32) / 255.0 - MEAN) / STD
        out.append(arr.transpose(2, 0, 1))
    return np.stack(out).astype(np.float32)


def embed(images: list[Image.Image]) -> np.ndarray:
    """L2-normalised CLS + mean-patch embeddings, (n, 768) float32."""
    with _lock:
        (vectors,) = _session().run(None, {"pixel_values": preprocess(images)})
    return vectors.astype(np.float32)


def rotations(img: Image.Image) -> list[Image.Image]:
    # rotate inside the circle: fill corners with the image's own border colour to avoid black wedges
    fill = img.resize((1, 1)).getpixel((0, 0))
    return [img.rotate(a, resample=Image.BICUBIC, fillcolor=fill) for a in ROTATIONS]


class Index:
    """Catalog embeddings, read from the catalog per query: only the few candidates a match weighs, so nothing is
    loaded at startup. Query vectors (a photo at every rotation) are computed once and can be kept for a re-price."""

    def __init__(self, db: sqlite3.Connection):
        self.db = db
        try:
            self.size = db.execute("SELECT COUNT(*) FROM coin_embeddings WHERE model = ?", (MODEL,)).fetchone()[0]
        except sqlite3.OperationalError:  # catalog without an index yet
            self.size = 0

    def __len__(self) -> int:
        return self.size

    @staticmethod
    def query(photo: bytes) -> np.ndarray:
        """A user photo at every rotation (a coin can be shot at any angle), (len(ROTATIONS), 768) float32."""
        return embed(rotations(coin_square(Image.open(io.BytesIO(photo)))))

    def scores(self, queries: list[np.ndarray], coin_ids: list[int]) -> dict[int, float]:
        """Similarity of the user's photos to specific catalog coins (coins without images are left out): for each
        photo, a coin's best image at the best rotation; then the mean over the photos."""
        if not queries or not coin_ids:
            return {}
        marks = ", ".join("?" * len(coin_ids))
        sql = f"SELECT coin_id, vector FROM coin_embeddings WHERE model = ? AND coin_id IN ({marks})"
        rows = self.db.execute(sql, [MODEL, *coin_ids]).fetchall()
        if not rows:
            return {}
        ids = [r[0] for r in rows]
        matrix = np.stack([np.frombuffer(r[1], dtype=np.float32) for r in rows])
        per_photo = []
        for q in queries:
            best: dict[int, float] = {}
            for coin_id, sim in zip(ids, (q @ matrix.T).max(axis=0).tolist(), strict=True):
                best[coin_id] = max(sim, best.get(coin_id, -1.0))
            per_photo.append(best)
        return {c: float(np.mean([p.get(c, 0.0) for p in per_photo])) for c in set(ids)}


def _torch_model():
    import torch
    from transformers import AutoModel

    class Embedder(torch.nn.Module):
        """DINOv2 + pooling: CLS token and mean of patch tokens, L2-normalised (robust for instance retrieval)."""

        def __init__(self):
            super().__init__()
            self.model = AutoModel.from_pretrained(MODEL)

        def forward(self, pixel_values):
            hidden = self.model(pixel_values=pixel_values).last_hidden_state
            vec = torch.cat([hidden[:, 0], hidden[:, 1:].mean(dim=1)], dim=1)
            return torch.nn.functional.normalize(vec, dim=1)

    return Embedder().eval()


def export() -> None:
    import torch

    ONNX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with torch.no_grad():
        torch.onnx.export(
            _torch_model(),
            (torch.zeros(1, 3, CROP, CROP),),
            str(ONNX_PATH),
            input_names=["pixel_values"],
            output_names=["embedding"],
            dynamic_axes={"pixel_values": {0: "batch"}, "embedding": {0: "batch"}},
            opset_version=17,
            dynamo=False,
        )
    print(f"wrote {ONNX_PATH} ({ONNX_PATH.stat().st_size / 1e6:.0f} MB)")


def build(db: sqlite3.Connection) -> None:
    """Embed catalog images missing from the index (torch, on the GPU when there is one)."""
    import torch

    device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    model = _torch_model().to(device)
    db.executescript(SCHEMA)
    todo = db.execute(
        "SELECT i.coin_id, i.position, i.local_path FROM coin_images i "
        "LEFT JOIN coin_embeddings e ON e.coin_id = i.coin_id AND e.position = i.position AND e.model = ? "
        "WHERE i.local_path IS NOT NULL AND e.coin_id IS NULL",
        (MODEL,),
    ).fetchall()
    print(f"{len(todo)} images to embed with {MODEL}")
    for start in range(0, len(todo), BATCH):
        batch = todo[start : start + BATCH]
        images, keys = [], []
        for coin_id, position, path in batch:
            try:
                images.append(square(Image.open(IMAGES_DIR / path)))
                keys.append((coin_id, position))
            except Exception as e:
                print(f"  skip {path}: {e}", file=sys.stderr)
        if not images:
            continue
        with torch.no_grad():
            vectors = model(torch.from_numpy(preprocess(images)).to(device)).cpu().numpy().astype(np.float32)
        db.executemany(
            "INSERT OR REPLACE INTO coin_embeddings VALUES (?, ?, ?, ?)",
            [(c, p, MODEL, v.tobytes()) for (c, p), v in zip(keys, vectors, strict=True)],
        )
        db.commit()
        done = start + len(batch)
        if done % (BATCH * 20) == 0 or done == len(todo):
            print(f"  {done}/{len(todo)}", flush=True)


if __name__ == "__main__":
    commands = {"build": lambda: build(connect()), "export": export}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        sys.exit("usage: python -m app.visual build|export")
    commands[sys.argv[1]]()
