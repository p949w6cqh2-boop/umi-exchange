#!/bin/bash
# Download HTMX and Alpine.js locally for CSP compliance.
# Run from project root: bash scripts/download_js.sh
set -e

JS_DIR="static/js"
mkdir -p "$JS_DIR"

echo "Downloading htmx 1.9.11..."
curl -sL "https://unpkg.com/htmx.org@1.9.11/dist/htmx.min.js" -o "$JS_DIR/htmx.min.js"

echo "Downloading Alpine.js 3.13.5..."
curl -sL "https://unpkg.com/alpinejs@3.13.5/dist/cdn.min.js" -o "$JS_DIR/alpine.min.js"

echo "Done. Files:"
ls -lh "$JS_DIR"/*.js
