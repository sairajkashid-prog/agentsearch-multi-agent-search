#!/usr/bin/env bash
# ==========================================================
#  AgentSearch - Multi-Agent Search Engine
#  One-click launcher for macOS / Linux
# ==========================================================
set -e
cd "$(dirname "$0")"

echo ""
echo " =========================================================="
echo "    AgentSearch  -  Multi-Agent Search Engine"
echo "    One-click launcher for macOS / Linux"
echo " =========================================================="
echo ""

# ---------- 1. Locate Python ----------
PY=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' >/dev/null 2>&1; then
            PY="$candidate"
            break
        fi
    fi
done

if [ -z "$PY" ]; then
    echo " [ERROR] Python 3.10 or newer was not found."
    echo ""
    echo " Install it from https://www.python.org/downloads/"
    echo " macOS:  brew install python"
    echo " Ubuntu: sudo apt install python3 python3-venv"
    echo ""
    read -r -p " Press Enter to close..." _
    exit 1
fi

echo " [1/4] Python found: $($PY --version)"
echo ""

# ---------- 2. Virtual environment ----------
if [ ! -x ".venv/bin/python" ]; then
    echo " [2/4] Creating virtual environment .venv ..."
    "$PY" -m venv .venv
else
    echo " [2/4] Virtual environment already exists - reusing it."
fi
VPY=".venv/bin/python"
echo ""

# ---------- 3. Dependencies ----------
echo " [3/4] Installing dependencies (first run can take 1-3 minutes)..."
echo ""
"$VPY" -m pip install --upgrade pip >/dev/null 2>&1 || true
"$VPY" -m pip install -r requirements.txt
echo ""

# ---------- 4. Port + launch ----------
PORT=8000
if [ -f ".env" ]; then
    ENV_PORT="$(grep -E '^PORT=' .env | tail -n 1 | cut -d= -f2 | tr -d '[:space:]' || true)"
    if [ -n "$ENV_PORT" ]; then PORT="$ENV_PORT"; fi
fi

URL="http://localhost:${PORT}"
echo " [4/4] Starting AgentSearch server..."
echo ""
echo " =========================================================="
echo "    App URL : ${URL}"
echo "    API docs: ${URL}/docs"
echo ""
echo "    Your browser will open automatically."
echo "    KEEP THIS WINDOW OPEN while using the app."
echo "    Press Ctrl+C here to stop the server."
echo " =========================================================="
echo ""

# Open the browser once the server has booted.
(
    sleep 6
    if command -v open >/dev/null 2>&1; then
        open "$URL" >/dev/null 2>&1 || true
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$URL" >/dev/null 2>&1 || true
    fi
) &

exec "$VPY" run.py
