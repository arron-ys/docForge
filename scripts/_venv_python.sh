#!/usr/bin/env bash
set -euo pipefail

if [[ ! -x ".venv/bin/python" ]]; then
  cat >&2 <<'EOF'
Error: .venv/bin/python is not available.

DocForge tests must run with the project virtual environment, not global python/python3.
Create or repair the environment first, for example:

  python3 -m venv .venv
  .venv/bin/python -m pip install -e ".[dev]"
EOF
  exit 1
fi

VENV_PYTHON=".venv/bin/python"
