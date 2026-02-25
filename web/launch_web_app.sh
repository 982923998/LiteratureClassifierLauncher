#!/bin/zsh
set -euo pipefail
setopt null_glob

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
RUNTIME_DIR="$SCRIPT_DIR/runtime"
BACKEND_PORT=8000
FRONTEND_PORT=5173

# Finder 启动 .app 时 PATH 往往很短，显式补全常见路径。
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

mkdir -p "$RUNTIME_DIR"

BACKEND_PID_FILE="$RUNTIME_DIR/backend.pid"
FRONTEND_PID_FILE="$RUNTIME_DIR/frontend.pid"
BACKEND_LOG="$RUNTIME_DIR/backend.log"
FRONTEND_LOG="$RUNTIME_DIR/frontend.log"
LAUNCH_LOG="$RUNTIME_DIR/launcher.log"

# Avoid npm/pip cache permission issues on some machines.
export NPM_CONFIG_CACHE="$RUNTIME_DIR/npm-cache"
export PIP_CACHE_DIR="$RUNTIME_DIR/pip-cache"

log() {
  local msg="$1"
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $msg" | tee -a "$LAUNCH_LOG"
}

show_info() {
  local msg="$1"
  log "INFO: $msg"
  /usr/bin/osascript -e "display notification \"$msg\" with title \"Literature Classifier\"" || true
}

show_error() {
  local msg="$1"
  log "ERROR: $msg"
  /usr/bin/osascript -e "display alert \"Literature Classifier\" message \"$msg\" as critical" || true
}

is_running() {
  local pid_file="$1"
  if [[ ! -f "$pid_file" ]]; then
    return 1
  fi

  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [[ -z "$pid" ]]; then
    return 1
  fi

  kill -0 "$pid" >/dev/null 2>&1
}

is_port_listening() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

pid_for_port() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | head -n 1
}

clean_stale_pid_file() {
  local pid_file="$1"

  if [[ ! -f "$pid_file" ]]; then
    return 0
  fi

  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [[ -z "$pid" ]]; then
    rm -f "$pid_file"
    return 0
  fi

  if ! kill -0 "$pid" >/dev/null 2>&1; then
    rm -f "$pid_file"
  fi
}

wait_for_http() {
  local url="$1"
  local retries="${2:-40}"

  for _ in $(seq 1 "$retries"); do
    if /usr/bin/curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

find_npm() {
  local candidate
  local -a candidates
  candidates=(
    "${NPM_BIN:-}"
    "$(command -v npm 2>/dev/null || true)"
    "/opt/homebrew/bin/npm"
    "/usr/local/bin/npm"
  )

  for candidate in "${candidates[@]}"; do
    if [[ -n "$candidate" && -x "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done

  return 1
}

start_backend() {
  clean_stale_pid_file "$BACKEND_PID_FILE"

  if is_port_listening "$BACKEND_PORT"; then
    local pid
    pid="$(pid_for_port "$BACKEND_PORT")"
    if [[ -n "$pid" ]]; then
      echo "$pid" >"$BACKEND_PID_FILE"
      log "Backend already running (PID $pid, port $BACKEND_PORT)."
    else
      log "Backend already running (port $BACKEND_PORT)."
    fi
    return
  fi

  if [[ ! -x "$BACKEND_DIR/.venv/bin/python" ]]; then
    show_error "未找到后端虚拟环境：$BACKEND_DIR/.venv。请先运行 ./web/setup_web_app.sh"
    exit 1
  fi

  log "Starting backend server..."
  (
    cd "$BACKEND_DIR"
    nohup "$BACKEND_DIR/.venv/bin/python" -m uvicorn main:app --host 127.0.0.1 --port "$BACKEND_PORT" >"$BACKEND_LOG" 2>&1 &
    echo $! >"$BACKEND_PID_FILE"
  )

  if wait_for_http "http://127.0.0.1:$BACKEND_PORT/api/health" 60; then
    log "Backend is ready."
  else
    show_error "后端启动失败，请查看日志: $BACKEND_LOG"
    exit 1
  fi
}

start_frontend() {
  local npm_bin
  local vite_bin
  if ! npm_bin="$(find_npm)"; then
    show_error "未找到 npm。请先安装 Node.js（建议安装 Homebrew Node）。"
    exit 1
  fi

  log "Using npm: $npm_bin"

  clean_stale_pid_file "$FRONTEND_PID_FILE"

  if is_port_listening "$FRONTEND_PORT"; then
    local pid
    pid="$(pid_for_port "$FRONTEND_PORT")"
    if [[ -n "$pid" ]]; then
      echo "$pid" >"$FRONTEND_PID_FILE"
      log "Frontend already running (PID $pid, port $FRONTEND_PORT)."
    else
      log "Frontend already running (port $FRONTEND_PORT)."
    fi
    return
  fi

  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    show_error "未找到前端依赖：$FRONTEND_DIR/node_modules。请先运行 ./web/setup_web_app.sh"
    exit 1
  fi

  vite_bin="$FRONTEND_DIR/node_modules/.bin/vite"
  if [[ ! -x "$vite_bin" ]]; then
    show_error "未找到 Vite 可执行文件：$vite_bin。请先运行 ./web/setup_web_app.sh"
    exit 1
  fi

  log "Starting frontend server..."
  (
    cd "$FRONTEND_DIR"
    nohup "$vite_bin" --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort >"$FRONTEND_LOG" 2>&1 &
    echo $! >"$FRONTEND_PID_FILE"
  )

  if wait_for_http "http://127.0.0.1:$FRONTEND_PORT" 60; then
    log "Frontend is ready."
  else
    show_error "前端启动失败，请查看日志: $FRONTEND_LOG"
    exit 1
  fi
}

open_browser() {
  local url="http://127.0.0.1:$FRONTEND_PORT"
  if /usr/bin/open "$url" >/dev/null 2>&1; then
    log "Browser opened at $url"
    return
  fi

  if /usr/bin/osascript -e "open location \"$url\"" >/dev/null 2>&1; then
    log "Browser opened via AppleScript at $url"
    return
  fi

  show_error "服务已启动，但无法自动打开浏览器。请手动访问：$url"
}

main() {
  log "Launching Literature Classifier Web..."
  show_info "正在启动服务，首次运行可能需要1-3分钟。"
  start_backend
  start_frontend
  open_browser
}

main "$@"
