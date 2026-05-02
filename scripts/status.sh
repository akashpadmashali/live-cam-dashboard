#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/.run"
BACKEND_PID_FILE="$RUN_DIR/backend.pid"
TUNNEL_PID_FILE="$RUN_DIR/tunnel.pid"
BACKEND_LOG="$RUN_DIR/backend.log"
TUNNEL_LOG="$RUN_DIR/tunnel.log"

print_status() {
  local name="$1"
  local pid_file="$2"

  if [[ ! -f "$pid_file" ]]; then
    echo "$name: stopped"
    return
  fi

  local pid
  pid="$(cat "$pid_file")"
  if kill -0 "$pid" >/dev/null 2>&1; then
    echo "$name: running (PID $pid)"
  else
    echo "$name: stale pid file ($pid)"
  fi
}

print_status "Backend" "$BACKEND_PID_FILE"
print_status "Tunnel" "$TUNNEL_PID_FILE"

if [[ -f "$TUNNEL_LOG" ]]; then
  url="$(grep -o 'https://[-a-z0-9]*\.trycloudflare\.com' "$TUNNEL_LOG" | tail -n 1 || true)"
  if [[ -n "$url" ]]; then
    echo "Public URL: $url"
  fi
fi

echo "Backend log: $BACKEND_LOG"
echo "Tunnel log: $TUNNEL_LOG"
