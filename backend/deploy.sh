#!/usr/bin/env bash
# Deploy the API to Vercel. The catalog and the vision model are not in git: they are copied into .deploy/ (git-ignored,
# bundled with the function by vercel.json) from the local data/ directory, then the CLI uploads the working tree.
set -euo pipefail
cd "$(dirname "$0")"

uv run python -m app.db export-slim .deploy/catalog.sqlite
[[ -f ../data/models/dinov2-small.onnx ]] || uv run --extra vision python -m app.visual export
cp ../data/models/dinov2-small.onnx .deploy/dinov2-small.onnx

vercel deploy --prod "$@"
