# Avers

**Take a photo of a coin, find out what it is and what it's worth.**

Avers is a small mobile app for coin collectors. You photograph a coin from both sides and it:

- **identifies** the coin (country, year, mint, denomination, type, catalog references) with Claude vision,
- **estimates its condition** on the French grading scale (B · TB · TTB · SUP · SPL · FDC),
- **values it** against comparable dealer listings, with an estimated range and typical shop prices,
- computes the **melt value** of its precious metal content from live spot prices,
- keeps a **personal collection** with quantities, notes and a running total value.

French UI with large text and big touch targets. Runs on iOS and Android.

## Architecture

```
mobile/   Expo (React Native) app: camera → estimate → collection
backend/  FastAPI service: Claude identification + valuation, catalog matching, spot prices, collection storage
data/     local only (git-ignored): catalog database, images, collection, uploaded photos
```

```
phone ──photo──▶ POST /estimate
                   ├─ Claude (claude-opus-5-5): identify coin → structured JSON
                   ├─ SQLite catalog: find comparable listings
                   ├─ gold-api.com + Frankfurter: spot price & FX → melt value
                   └─ Claude: value range from comparables + melt
       ◀─result─┘
phone ──save──▶ POST /collection  (separate SQLite file, never touched by catalog imports)
```

- **Multi-source catalog**: every listing carries a `source`, so other dealers and countries can be added next to the first one.
- **Multi-currency**: catalog prices and melt values are converted to the currency chosen in the app (EUR, CHF, USD, GBP, CAD).

## Running it

### API

Requires [uv](https://docs.astral.sh/uv/) and Anthropic credentials (`ant auth login`, or `ANTHROPIC_API_KEY`, see `backend/.env.example`).

```bash
cd backend
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The catalog lives in `data/coins.sqlite` (schema in `backend/app/db.py`). It is populated by import tooling that is not part of this repository. Without it the app still identifies coins and computes melt values. It just has no comparables to show.

### App

```bash
cd mobile
cp .env.example .env.local   # set EXPO_PUBLIC_API_URL to your computer's LAN IP
npm install --legacy-peer-deps
npx expo start
```

Scan the QR code with Expo Go on the phone (same Wi-Fi as the API). The server address can also be changed in the app under **Réglages**.

## Development

```bash
cd backend && uv run pytest && uv run ruff check app tests && uv run ruff format app tests
cd mobile && npx tsc --noEmit && npx expo-doctor
```

CI runs both on every push and pull request.

## Disclaimer

Estimates are indicative only: they combine dealer asking prices, an AI-estimated grade and the metal price of the day. Have valuable coins appraised by a professional before selling.

## License

[MIT](LICENSE)
