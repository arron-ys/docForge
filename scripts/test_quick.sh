#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source scripts/_venv_python.sh

exec "$VENV_PYTHON" -m pytest \
  tests/contract/test_api_sprint2.py \
  tests/unit/test_schemas.py \
  tests/unit/test_state_store.py \
  tests/unit/test_user_facing_errors.py \
  tests/unit/test_workflow_diagnostics.py \
  -q "$@"
