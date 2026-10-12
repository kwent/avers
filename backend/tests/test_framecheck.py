import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import main
from app.framecheck import GUIDE_PADDING, check_frame

S = 800


def synthetic_coin(scale=0.9, dx=0.0, brightness=1.0, blur=0.0, glare=False, coin=True) -> bytes:
    """A textured disc on a noisy background, laid out like the app's guide-circle crop."""
    rng = np.random.default_rng(1)
    img = np.clip(70 + rng.normal(0, 8, (S, S, 3)), 0, 255).astype(np.uint8)
    if coin:
        r = int(S / GUIDE_PADDING / 2 * scale)
        c = (S // 2 + int(dx * S), S // 2)
        cv2.circle(img, c, r, (60, 170, 215), -1)
        cv2.circle(img, c, r, (30, 110, 160), 6)
        texture = rng.integers(0, 2, (S, S)).astype(bool)
        mask = np.zeros((S, S), np.uint8)
        cv2.circle(mask, c, int(r * 0.85), 255, -1)
        img[(mask > 0) & texture] = (40, 130, 180)
        if glare:
            cv2.circle(img, c, int(r * 0.6), (255, 255, 255), -1)
    img = (img * brightness).astype(np.uint8)
    if blur:
        img = cv2.GaussianBlur(img, (0, 0), blur)
    return cv2.imencode(".jpg", img)[1].tobytes()


@pytest.mark.parametrize(
    "kwargs,status",
    [
        ({}, "ok"),
        ({"coin": False}, "no_coin"),
        ({"scale": 0.55}, "too_small"),
        ({"scale": 1.09}, "too_big"),
        ({"scale": 0.75, "dx": 0.1}, "off_center"),
        ({"blur": 6}, "blurry"),
        ({"brightness": 0.2}, "too_dark"),
        ({"glare": True}, "glare"),
    ],
)
def test_check_frame(kwargs, status):
    assert check_frame(synthetic_coin(**kwargs)).status == status


def test_ok_frame_reports_coin_geometry():
    result = check_frame(synthetic_coin(scale=0.9))
    assert result.coin["r"] == pytest.approx(0.9, abs=0.08)
    assert abs(result.coin["x"]) < 0.05


def test_frame_check_endpoint():
    client = TestClient(main.app)
    res = client.post("/frame-check", files={"frame": ("f.jpg", synthetic_coin(), "image/jpeg")})
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert client.post("/frame-check", files={"frame": ("f.jpg", b"junk", "image/jpeg")}).status_code == 400
