"""Visual search: find catalog coins that look like the user's photos.

Each catalog image gets a DINOv2 embedding (stored in coins.sqlite). A query embeds the user's photos at several
rotations (a coin can be shot at any angle) and ranks catalog coins by their best-matching image.

Optional: needs the `vision` extra (torch + transformers). Without it, `available()` is False and the API simply
skips visual candidates.

Build/refresh the index:  uv run --extra vision python -m app.visual build
"""

import io
import sqlite3
import sys
import threading
from functools import lru_cache

import numpy as np
from PIL import Image, ImageOps

from app.db import IMAGES_DIR, connect

MODEL = "facebook/dinov2-small"
ROTATIONS = (0, 45, 90, 135, 180, 225, 270, 315)
BATCH = 64

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
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError:
        return False
    return True


@lru_cache(maxsize=1)
def _model():
    import torch
    from transformers import AutoImageProcessor, AutoModel

    device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    processor = AutoImageProcessor.from_pretrained(MODEL)
    model = AutoModel.from_pretrained(MODEL).to(device).eval()
    return processor, model, device


_lock = threading.Lock()


def square(img: Image.Image) -> Image.Image:
    """Centre square crop, RGB, EXIF-rotated."""
    img = ImageOps.exif_transpose(img).convert("RGB")
    side = min(img.size)
    left, top = (img.width - side) // 2, (img.height - side) // 2
    return img.crop((left, top, left + side, top + side))


def embed(images: list[Image.Image]) -> np.ndarray:
    import torch

    processor, model, device = _model()
    with _lock, torch.no_grad():
        inputs = processor(images=images, return_tensors="pt").to(device)
        out = model(**inputs)
        # CLS token + mean of patch tokens: robust for fine-grained instance retrieval
        cls = out.last_hidden_state[:, 0]
        patches = out.last_hidden_state[:, 1:].mean(dim=1)
        vec = torch.cat([cls, patches], dim=1)
        vec = torch.nn.functional.normalize(vec, dim=1)
    return vec.cpu().numpy().astype(np.float32)


def rotations(img: Image.Image) -> list[Image.Image]:
    # rotate inside the circle: fill corners with the image's own border colour to avoid black wedges
    fill = img.resize((1, 1)).getpixel((0, 0))
    return [img.rotate(a, resample=Image.BICUBIC, fillcolor=fill) for a in ROTATIONS]


class Index:
    """All catalog embeddings in memory (≈ 19k × 768 float32 ≈ 60 MB)."""

    def __init__(self, db: sqlite3.Connection):
        db.executescript(SCHEMA)
        rows = db.execute("SELECT coin_id, vector FROM coin_embeddings WHERE model = ?", (MODEL,)).fetchall()
        self.coin_ids = np.array([r[0] for r in rows], dtype=np.int64)
        self.matrix = np.stack([np.frombuffer(r[1], dtype=np.float32) for r in rows]) if rows else None

    def __len__(self) -> int:
        return len(self.coin_ids)

    def _per_photo_best(self, photos: list[bytes], mask: np.ndarray | None = None) -> list[dict[int, float]]:
        """For each user photo: {coin_id: best similarity over that coin's images and the query rotations}."""
        ids, matrix = self.coin_ids, self.matrix
        if mask is not None:
            ids, matrix = ids[mask], matrix[mask]
        out = []
        for data in photos:
            queries = embed(rotations(square(Image.open(io.BytesIO(data)))))
            sims = (queries @ matrix.T).max(axis=0)  # best rotation per catalog image
            best: dict[int, float] = {}
            for coin_id, sim in zip(ids.tolist(), sims.tolist(), strict=True):
                if sim > best.get(coin_id, -1.0):
                    best[coin_id] = sim
            out.append(best)
        return out

    @staticmethod
    def _combine(per_photo: list[dict[int, float]]) -> dict[int, float]:
        """Score = mean over the user's photos of each coin's best image similarity."""
        coins = set().union(*per_photo) if per_photo else set()
        return {c: float(np.mean([p.get(c, 0.0) for p in per_photo])) for c in coins}

    def search(self, photos: list[bytes], k: int = 12) -> list[tuple[int, float]]:
        """Top-k (coin_id, score) over the whole catalog."""
        if self.matrix is None or not photos:
            return []
        scores = self._combine(self._per_photo_best(photos))
        return sorted(scores.items(), key=lambda x: -x[1])[:k]

    def scores(self, photos: list[bytes], coin_ids: list[int]) -> dict[int, float]:
        """Similarity of the user's photos to specific catalog coins (coins without images are left out)."""
        if self.matrix is None or not photos or not coin_ids:
            return {}
        mask = np.isin(self.coin_ids, coin_ids)
        if not mask.any():
            return {}
        return self._combine(self._per_photo_best(photos, mask))


def build(db: sqlite3.Connection) -> None:
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
        vectors = embed(images)
        db.executemany(
            "INSERT OR REPLACE INTO coin_embeddings VALUES (?, ?, ?, ?)",
            [(c, p, MODEL, v.tobytes()) for (c, p), v in zip(keys, vectors, strict=True)],
        )
        db.commit()
        done = start + len(batch)
        if done % (BATCH * 20) == 0 or done == len(todo):
            print(f"  {done}/{len(todo)}", flush=True)


if __name__ == "__main__":
    if sys.argv[1:] != ["build"]:
        sys.exit("usage: python -m app.visual build")
    build(connect())
