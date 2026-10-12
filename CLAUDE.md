# Avers

Coin identification + valuation app. See README.md for architecture.

- `backend/`: FastAPI + SQLite, managed with uv. Test: `uv run pytest`; lint: `uv run ruff check app tests && uv run ruff format app tests`.
- `mobile/`: Expo app (routes in `src/app/`). Read `mobile/AGENTS.md` before touching Expo APIs. Typecheck: `npx tsc --noEmit`; deps: `npx expo install` (falls back to `npm install --legacy-peer-deps` on peer conflicts).

Rules:
- Never commit anything under `data/` or `backend/scrapers/` (git-ignored on purpose).
- Keep price sources pluggable (`coins.source`) and amounts currency-aware; the UI is French, large-text and accessible (≥56px touch targets).
- Claude calls live in `backend/app/identify.py` (model `claude-opus-5-5`, structured outputs, server-side refusal fallbacks).
