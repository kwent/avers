"""Fast, local quality check of a camera frame before the real capture (no AI call).

The app sends the square crop around its on-screen guide circle; the guide circle is centred
with diameter = side / GUIDE_PADDING. We look for the coin and grade framing, focus and light.
"""

from dataclasses import asdict, dataclass

import cv2
import numpy as np

GUIDE_PADDING = 1.1  # the app crops 10% beyond the guide circle
WORK_SIZE = 480

# thresholds (tuned on phone photos of coins at WORK_SIZE)
MAX_OFFSET = 0.18  # coin centre distance from guide centre, in guide radii
MIN_SIZE = 0.72  # coin radius / guide radius
MAX_SIZE = 1.06
MIN_SHARPNESS = 60.0  # variance of the Laplacian inside the coin
MIN_BRIGHTNESS = 55.0  # mean grey level inside the coin
MAX_GLARE = 0.12  # share of blown-out pixels inside the coin

STATUSES = ("ok", "no_coin", "too_dark", "off_center", "too_small", "too_big", "blurry", "glare")


@dataclass
class FrameCheck:
    status: str  # one of STATUSES
    coin: dict | None = None  # {"x", "y", "r"} in guide-relative units (centre 0,0; guide radius 1)
    sharpness: float | None = None
    brightness: float | None = None
    glare: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _find_coin(gray: np.ndarray, guide_r: float) -> tuple[float, float, float] | None:
    blurred = cv2.medianBlur(gray, 5)
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.5,
        minDist=gray.shape[0],  # one coin
        param1=110,
        param2=40,
        minRadius=int(guide_r * 0.45),
        maxRadius=int(guide_r * 1.15),
    )
    if circles is None:
        return None
    x, y, r = circles[0][0]
    return float(x), float(y), float(r)


def check_frame(data: bytes) -> FrameCheck:
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError("unreadable image")
    h, w = img.shape
    side = min(h, w)
    y0, x0 = (h - side) // 2, (w - side) // 2
    img = img[y0 : y0 + side, x0 : x0 + side]
    gray = cv2.resize(img, (WORK_SIZE, WORK_SIZE), interpolation=cv2.INTER_AREA)
    c = WORK_SIZE / 2
    guide_r = WORK_SIZE / GUIDE_PADDING / 2

    found = _find_coin(gray, guide_r)
    if found is None:
        # too dark to see edges is the more useful hint than "no coin"
        guide = np.zeros_like(gray)
        cv2.circle(guide, (int(c), int(c)), int(guide_r), 255, -1)
        level = float(gray[guide > 0].mean())
        return FrameCheck("too_dark" if level < MIN_BRIGHTNESS else "no_coin", brightness=round(level, 1))
    x, y, r = found
    coin = {"x": round((x - c) / guide_r, 3), "y": round((y - c) / guide_r, 3), "r": round(r / guide_r, 3)}

    mask = np.zeros_like(gray)
    cv2.circle(mask, (int(x), int(y)), int(r * 0.9), 255, -1)
    inside = mask > 0
    brightness = float(gray[inside].mean())
    glare = float((gray[inside] >= 250).mean())
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    sharpness = float(laplacian[inside].var())
    result = FrameCheck("ok", coin, round(sharpness, 1), round(brightness, 1), round(glare, 3))

    offset = float(np.hypot(coin["x"], coin["y"]))
    if brightness < MIN_BRIGHTNESS:
        result.status = "too_dark"
    elif offset > MAX_OFFSET:
        result.status = "off_center"
    elif coin["r"] < MIN_SIZE:
        result.status = "too_small"
    elif coin["r"] > MAX_SIZE:
        result.status = "too_big"
    elif sharpness < MIN_SHARPNESS:
        result.status = "blurry"
    elif glare > MAX_GLARE:
        result.status = "glare"
    return result
