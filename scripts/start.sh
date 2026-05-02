#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/.run"
BACKEND_PID_FILE="$RUN_DIR/backend.pid"
TUNNEL_PID_FILE="$RUN_DIR/tunnel.pid"
BACKEND_LOG="$RUN_DIR/backend.log"
TUNNEL_LOG="$RUN_DIR/tunnel.log"
CLOUDFLARED_BIN="$ROOT_DIR/.cloudflared-local/usr/bin/cloudflared"
URL_PATTERN='https://[-a-z0-9]*\.trycloudflare\.com'

mkdir -p "$RUN_DIR"

is_running() {
  local pid_file="$1"
  if [[ ! -f "$pid_file" ]]; then
    return 1
  fi

  local pid
  pid="$(cat "$pid_file")"
  kill -0 "$pid" >/dev/null 2>&1
}

remove_stale_pid() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]] && ! is_running "$pid_file"; then
    rm -f "$pid_file"
  fi
}

wait_for_url() {
  local attempts=20
  local delay=1
  local url=""

  for ((i = 1; i <= attempts; i++)); do
    url="$(grep -o "$URL_PATTERN" "$TUNNEL_LOG" | tail -n 1 || true)"
    if [[ -n "$url" ]]; then
      echo "$url"
      return 0
    fi
    sleep "$delay"
  done

  return 1
}

start_backend() {
  remove_stale_pid "$BACKEND_PID_FILE"
  if is_running "$BACKEND_PID_FILE"; then
    echo "Backend already running with PID $(cat "$BACKEND_PID_FILE")"
    return
  fi

  echo "Starting backend..."
  nohup python3 "$ROOT_DIR/app.py" >"$BACKEND_LOG" 2>&1 &
  echo $! >"$BACKEND_PID_FILE"
  sleep 2
  echo "Backend PID: $(cat "$BACKEND_PID_FILE")"
  echo "Backend log: $BACKEND_LOG"
}

start_tunnel() {
  remove_stale_pid "$TUNNEL_PID_FILE"
  if [[ ! -x "$CLOUDFLARED_BIN" ]]; then
    echo "cloudflared binary not found at $CLOUDFLARED_BIN"
    echo "Download or unpack cloudflared first."
    return 1
  fi

  if is_running "$TUNNEL_PID_FILE"; then
    echo "Tunnel already running with PID $(cat "$TUNNEL_PID_FILE")"
    return
  fi

  echo "Starting quick tunnel..."
  nohup "$CLOUDFLARED_BIN" tunnel --url http://127.0.0.1:8501 >"$TUNNEL_LOG" 2>&1 &
  echo $! >"$TUNNEL_PID_FILE"
  sleep 2
  echo "Tunnel PID: $(cat "$TUNNEL_PID_FILE")"
  echo "Tunnel log: $TUNNEL_LOG"

  local url
  url="$(wait_for_url || true)"
  if [[ -n "$url" ]]; then
    echo "Public URL: $url"
  else
    echo "Public URL not found yet after waiting. Check $TUNNEL_LOG."
  fi
}

start_backend
start_tunnel
