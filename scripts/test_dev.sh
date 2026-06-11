#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source scripts/_venv_python.sh

test_paths=(tests/unit)
if [[ -d tests/contract ]]; then
  test_paths+=(tests/contract)
fi

exec "$VENV_PYTHON" -m pytest "${test_paths[@]}" -m "not slow and not external and not legacy" -q "$@"
