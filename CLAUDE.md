# Avers

Coin identification + valuation app. See README.md for architecture.

- `backend/`: FastAPI + SQLite, managed with uv. Test: `uv run pytest`; lint: `uv run ruff check app tests bench && uv run ruff format app tests bench`.
- `mobile/`: Expo app (routes in `src/app/`), styled with NativeWind; tokens in `src/theme/tokens.js`, primitives in `src/components/ui.tsx`; format with `npx prettier --write src`. Read `mobile/AGENTS.md` before touching Expo APIs. Typecheck: `npx tsc --noEmit`; deps: `npx expo install` (falls back to `npm install --legacy-peer-deps` on peer conflicts).

Rules:
- Never commit anything under `data/` or `backend/scrapers/` (git-ignored on purpose).
- Keep price sources pluggable (`coins.source`) and amounts currency-aware; the UI is French, large-text and accessible (≥56px touch targets).
- One vision-model call per estimate, in `backend/app/identify.py`, through the Vercel AI Gateway (OpenAI-compatible API, strict JSON schema, gateway fallback models). The model is configuration (`VISION_MODEL`); compare candidates with `bench/models.py` before changing the default. Matching (`app/matching.py`), year checks (`app/years.py`) and pricing (`app/pricing.py`) are plain code: keep them LLM-free.
- Prices come from catalog listings first; Numista (`app/numista.py`, optional, free quota, cached) only fills in when the catalog has no listing. Unsure of a fact (e.g. the year)? Ask the user rather than guess.
