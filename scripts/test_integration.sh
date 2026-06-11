#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source scripts/_venv_python.sh
exec "$VENV_PYTHON" -m pytest tests/integration -m "not external" -q "$@"
