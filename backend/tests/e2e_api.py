"""The API the iOS e2e flows talk to (mobile/scripts/e2e-ios.sh): the real app, except that the year the vision model
reads can be turned into another one (E2E_MISREAD_YEARS="1851:1861"), so the flows reach the year question with a
model that reads the fixture right. Run: uv run uvicorn tests.e2e_api:app
"""

import os

from app import identify, pipeline
from app.main import app  # noqa: F401  (served by uvicorn)

MISREAD = {
    int(a): int(b) for a, b in (p.split(":") for p in os.environ.get("E2E_MISREAD_YEARS", "").split(",") if ":" in p)
}
_identify = identify.identify


def _misread(images, language):
    coin = _identify(images, language)
    if coin.year in MISREAD:
        pipeline.set_year(coin, MISREAD[coin.year])
    return coin


identify.identify = _misread
