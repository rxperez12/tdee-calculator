#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

command -v uv >/dev/null || { echo "uv not found: https://docs.astral.sh/uv/"; exit 1; }

uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy
uv run --locked pytest --cov
