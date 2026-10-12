#!/usr/bin/env bash
# Run the Maestro e2e flows against Expo Go in the iOS Simulator.
#
# Prereqs: Xcode, Maestro (brew install mobile-dev-inc/tap/maestro), a JDK, the API running on :8000,
# and `npx expo start` running (or pass --start). Coin photos go in .maestro/fixtures/coin-{front,back}.jpg.
#
# Usage: scripts/e2e-ios.sh [--start] [flow.yaml ...]   (default: all flows in .maestro/)
set -euo pipefail
cd "$(dirname "$0")/.."

DEVICE="${E2E_DEVICE:-iPhone 17 Pro}"
START_EXPO=0
if [[ "${1:-}" == "--start" ]]; then START_EXPO=1; shift; fi
FLOWS=("${@:-.maestro}")

if [[ -z "${JAVA_HOME:-}" ]] && command -v brew >/dev/null && brew --prefix openjdk@21 >/dev/null 2>&1; then
  export JAVA_HOME="$(brew --prefix openjdk@21)/libexec/openjdk.jdk/Contents/Home"
fi

udid="$(xcrun simctl list devices available -j | python3 -c "
import json, sys
devices = [d for r in json.load(sys.stdin)['devices'].values() for d in r if d['name'] == sys.argv[1]]
booted = [d for d in devices if d['state'] == 'Booted']
print((booted or devices)[0]['udid'])
" "$DEVICE")"
xcrun simctl boot "$udid" 2>/dev/null || true
xcrun simctl bootstatus "$udid" -b >/dev/null

for f in .maestro/fixtures/coin-front.jpg .maestro/fixtures/coin-back.jpg; do
  [[ -f "$f" ]] || { echo "missing fixture $f" >&2; exit 1; }
done
# Stamp each fixture with its own far-future capture date so the flow can pick it by its
# accessibility label ("Photo, January 02, 2099, ...") no matter how many copies past runs added.
stamped="$(mktemp -d)"
uv run --quiet --no-project --with pillow python - "$stamped" <<'PY'
import sys
from PIL import Image
out = sys.argv[1]
for side, date in (("front", "2099:01:02 12:00:00"), ("back", "2099:01:01 12:00:00")):
    img = Image.open(f".maestro/fixtures/coin-{side}.jpg")
    exif = img.getexif()
    exif[0x0132] = date  # DateTime
    exif.get_ifd(0x8769)[0x9003] = date  # DateTimeOriginal
    img.save(f"{out}/coin-{side}.jpg", exif=exif, quality=95)
PY
xcrun simctl addmedia "$udid" "$stamped/coin-front.jpg" "$stamped/coin-back.jpg"

if [[ $START_EXPO == 1 ]]; then
  npx expo start --ios --port 8081 >/tmp/avers-expo.log 2>&1 &
  trap 'kill %1 2>/dev/null || true' EXIT
  until curl -sf http://localhost:8081/status >/dev/null; do sleep 2; done
fi

curl -sf "${EXPO_PUBLIC_API_URL:-http://localhost:8000}/health" >/dev/null || { echo "API not reachable" >&2; exit 1; }

maestro --device "$udid" test "${FLOWS[@]}"
