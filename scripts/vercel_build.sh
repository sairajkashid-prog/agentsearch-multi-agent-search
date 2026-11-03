#!/usr/bin/env bash
# Vercel build step: publish the chat frontend as static assets.
# The frontend/ folder stays the single source of truth; we only copy it here
# so the deployed HTML keeps using the same /static/... asset paths as local.
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf public
mkdir -p public/static

cp frontend/index.html public/index.html
cp frontend/styles.css public/static/styles.css
cp frontend/app.js     public/static/app.js

echo "Vercel build: static frontend prepared in ./public"
ls -R public
