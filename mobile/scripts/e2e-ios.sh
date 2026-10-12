#!/usr/bin/env bash
# Run the Maestro e2e flows against Expo Go in the iOS Simulator.
#
# Prereqs: Xcode, Maestro (brew install mobile-dev-inc/tap/maestro), a JDK, uv, and `npx expo start` running
# (or pass --start). The flows talk to a throwaway API started here on $E2E_API_PORT (default 8001) with its own
# empty collection, so test runs never touch real data; the catalog database is shared read-only. Fixture photos go in .maestro/fixtures/: coin-front.jpg, coin-back.jpg and not-coin.jpg (any non-coin object).
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

for f in .maestro/fixtures/{coin-front,coin-back,not-coin}.jpg; do
  [[ -f "$f" ]] || { echo "missing fixture $f" >&2; exit 1; }
done
# Add the fixtures to the simulator library once (they pile up otherwise and push each other out of view).
marker="${XDG_CACHE_HOME:-$HOME/.cache}/avers-e2e/$udid-$(cat .maestro/fixtures/*.jpg | shasum | cut -c1-12)"
if [[ ! -f "$marker" ]]; then
# Stamp each fixture with its own far-future capture date so the flow can pick it by its
# accessibility label ("Photo, January 02, 2099, ...") no matter how many copies past runs added.
stamped="$(mktemp -d)"
uv run --quiet --no-project --with pillow python - "$stamped" <<'PY'
import sys
from PIL import Image
out = sys.argv[1]
for name, date in (("coin-front", "2099:01:02 12:00:00"), ("coin-back", "2099:01:01 12:00:00"),
                   ("not-coin", "2099:01:03 12:00:00")):
    img = Image.open(f".maestro/fixtures/{name}.jpg")
    exif = img.getexif()
    exif[0x0132] = date  # DateTime
    exif.get_ifd(0x8769)[0x9003] = date  # DateTimeOriginal
    img.save(f"{out}/{name}.jpg", exif=exif, quality=95)
PY
xcrun simctl addmedia "$udid" "$stamped/coin-front.jpg" "$stamped/coin-back.jpg" "$stamped/not-coin.jpg"
mkdir -p "$(dirname "$marker")" && touch "$marker"
fi

pids=()
cleanup() { for p in "${pids[@]}"; do kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT

if [[ $START_EXPO == 1 ]]; then
  npx expo start --ios --port 8081 >/tmp/avers-expo.log 2>&1 &
  pids+=($!)
  until curl -sf http://localhost:8081/status >/dev/null; do sleep 2; done
fi

port="${E2E_API_PORT:-8001}"
api_data="$(mktemp -d)"
(
  cd ../backend
  COLLECTION_DB="$api_data/collection.sqlite" UPLOADS_DIR="$api_data/uploads" \
    exec uv run uvicorn app.main:app --host 127.0.0.1 --port "$port"
) >"$api_data/api.log" 2>&1 &
pids+=($!)
until curl -sf "http://localhost:$port/health" >/dev/null; do sleep 1; done

# Start from a clean app: a picker or sheet left open by an aborted run blocks every flow
xcrun simctl terminate "$udid" host.exp.Exponent 2>/dev/null || true

maestro --device "$udid" test -e API_URL="http://localhost:$port" "${FLOWS[@]}"
