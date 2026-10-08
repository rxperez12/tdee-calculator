#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

command -v uv >/dev/null || { echo "uv not found: https://docs.astral.sh/uv/"; exit 1; }
uv sync --quiet
exec uv run tdee-calculator
