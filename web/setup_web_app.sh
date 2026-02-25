#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
RUNTIME_DIR="$SCRIPT_DIR/runtime"

mkdir -p "$RUNTIME_DIR"
export NPM_CONFIG_CACHE="$RUNTIME_DIR/npm-cache"
export PIP_CACHE_DIR="$RUNTIME_DIR/pip-cache"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

echo "[setup] backend: creating/updating venv"
if [[ ! -x "$BACKEND_DIR/.venv/bin/python" ]]; then
  /usr/bin/python3 -m venv "$BACKEND_DIR/.venv"
fi

echo "[setup] backend: upgrading pip tooling"
"$BACKEND_DIR/.venv/bin/python" -m pip install --upgrade pip setuptools wheel

"$BACKEND_DIR/.venv/bin/pip" install -r "$BACKEND_DIR/requirements.txt"

echo "[setup] frontend: installing npm packages"
(
  cd "$FRONTEND_DIR"
  npm install
)

echo "[setup] done"
