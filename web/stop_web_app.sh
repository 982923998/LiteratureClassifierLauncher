#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_DIR="$SCRIPT_DIR/runtime"
BACKEND_PID_FILE="$RUNTIME_DIR/backend.pid"
FRONTEND_PID_FILE="$RUNTIME_DIR/frontend.pid"

stop_by_pid_file() {
  local pid_file="$1"
  local name="$2"

  if [[ ! -f "$pid_file" ]]; then
    echo "$name: no pid file"
    return
  fi

  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"

  if [[ -z "$pid" ]]; then
    echo "$name: empty pid"
    rm -f "$pid_file"
    return
  fi

  if kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" >/dev/null 2>&1 || true
    sleep 0.2
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
    echo "$name: stopped pid $pid"
  else
    echo "$name: pid $pid not running"
  fi

  rm -f "$pid_file"
}

stop_by_pid_file "$BACKEND_PID_FILE" "backend"
stop_by_pid_file "$FRONTEND_PID_FILE" "frontend"

# Fallback cleanup for stale launched processes not tracked by pid files.
pkill -f "uvicorn main:app --host 127.0.0.1 --port 8000" >/dev/null 2>&1 || true
pkill -f "vite --host 127.0.0.1 --port 5173" >/dev/null 2>&1 || true

# Last-resort cleanup by listening ports.
for port in 8000 5173; do
  pids="$(lsof -nP -iTCP:${port} -sTCP:LISTEN -t 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    echo "$pids" | xargs kill -9 >/dev/null 2>&1 || true
    echo "port $port: force killed listener pids"
  fi
done
