#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend/docforge-web"

if [[ ! -d "$FRONTEND_DIR" ]]; then
  printf "Error: frontend directory not found: %s\n" "$FRONTEND_DIR" >&2
  exit 1
fi

if [[ ! -f "$FRONTEND_DIR/package.json" ]]; then
  printf "Error: frontend package.json not found: %s/package.json\n" "$FRONTEND_DIR" >&2
  exit 1
fi

if ! command -v pnpm >/dev/null 2>&1; then
  cat >&2 <<'EOF'
Error: pnpm is not available.

DocForge frontend checks must use the Node.js/pnpm toolchain.
Do not install pnpm into the Python .venv. Install Node.js and enable Corepack, for example:

  corepack enable
  corepack prepare pnpm@latest --activate
EOF
  exit 1
fi

cd "$FRONTEND_DIR"

# package.json build runs vue-tsc and Vite build. Extra args are passed to the build script.
if [[ "$#" -gt 0 ]]; then
  exec pnpm run build -- "$@"
fi

exec pnpm run build
