#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
BACKEND_BASE_URL="${BACKEND_BASE_URL:-}"

rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR/static"

cp "$ROOT_DIR/frontend/index.html" "$DIST_DIR/index.html"
cp "$ROOT_DIR/frontend/styles.css" "$DIST_DIR/static/styles.css"
cp "$ROOT_DIR/frontend/app.js" "$DIST_DIR/static/app.js"

escaped_url="$(printf '%s' "$BACKEND_BASE_URL" | sed 's/[\/&]/\\&/g')"
sed "s/__BACKEND_BASE_URL__/${escaped_url}/g" \
  "$ROOT_DIR/frontend/config.template.js" >"$DIST_DIR/config.js"

echo "Built Pages assets into $DIST_DIR"
if [[ -n "$BACKEND_BASE_URL" ]]; then
  echo "Configured backend base URL: $BACKEND_BASE_URL"
else
  echo "No BACKEND_BASE_URL provided. Frontend will fall back to manual entry."
fi
