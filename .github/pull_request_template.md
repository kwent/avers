## What

## Why

## Checks

- [ ] `cd backend && uv run pytest && uv run ruff check app tests bench && uv run ruff format --check app tests bench`
- [ ] `cd mobile && npx tsc --noEmit`
- [ ] No secrets, catalog data (`data/`) or import tooling (`backend/scrapers/`) in the diff
