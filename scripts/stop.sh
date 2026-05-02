#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/.run"
BACKEND_PID_FILE="$RUN_DIR/backend.pid"
TUNNEL_PID_FILE="$RUN_DIR/tunnel.pid"

stop_process() {
  local name="$1"
  local pid_file="$2"

  if [[ ! -f "$pid_file" ]]; then
    echo "$name is not running."
    return
  fi

  local pid
  pid="$(cat "$pid_file")"
  if kill -0 "$pid" >/dev/null 2>&1; then
    echo "Stopping $name (PID $pid)..."
    kill "$pid"
  else
    echo "$name PID file exists, but process is already gone."
  fi

  rm -f "$pid_file"
}

stop_process "Tunnel" "$TUNNEL_PID_FILE"
stop_process "Backend" "$BACKEND_PID_FILE"
