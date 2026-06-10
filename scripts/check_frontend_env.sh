#!/usr/bin/env bash
set -u

echo "DocForge frontend environment check"
echo

missing=0

print_found() {
  name="$1"
  path="$2"
  version="$3"
  printf "%-9s found %s (%s)\n" "$name:" "$version" "$path"
}

print_missing() {
  name="$1"
  printf "%-9s missing\n" "$name:"
  missing=1
}

check_command() {
  name="$1"
  if command -v "$name" >/dev/null 2>&1; then
    path="$(command -v "$name")"
    version="$("$name" -v 2>/dev/null || "$name" --version 2>/dev/null || true)"
    version="$(printf "%s" "$version" | head -n 1)"
    [ -n "$version" ] || version="version unknown"
    print_found "$name" "$path" "$version"

    case "$name:$path" in
      node:/Applications/Codex.app/*|node:/private/tmp/*|node:*"/.codex/tmp/"*)
        echo "          warning: this Node path looks temporary or Codex-managed; use a system Node.js install for long-running frontend development."
        ;;
    esac
  else
    print_missing "$name"
  fi
}

check_command node
check_command npm
check_command corepack
check_command pnpm

echo

if ! command -v node >/dev/null 2>&1; then
  cat <<'EOF'
Node.js is required for the Vue/Vite frontend.
On macOS, install a system Node.js runtime, for example:
  brew install node
EOF
fi

if ! command -v pnpm >/dev/null 2>&1; then
  cat <<'EOF'
pnpm is missing.
pnpm is a Node.js package manager, not a Python .venv package.

After installing Node.js, enable pnpm with Corepack:
  corepack enable
  corepack prepare pnpm@latest --activate
EOF
fi

if ! command -v corepack >/dev/null 2>&1; then
  cat <<'EOF'
Corepack is missing.
Install a full system Node.js distribution first, then use Corepack to activate pnpm.
EOF
fi

echo
if [ "$missing" -eq 0 ]; then
  echo "Frontend toolchain looks ready."
  exit 0
fi

echo "Frontend toolchain is incomplete. Install the missing tools before running pnpm install / pnpm dev."
exit 1
