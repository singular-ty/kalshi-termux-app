#!/usr/bin/env bash
# Kalshi Termux Portal launcher
set -euo pipefail
cd "$(dirname "$0")"

export PYTHONPATH="${PYTHONPATH:-}:$(pwd)"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8787}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[-] python3 not found. On Termux: pkg install python"
  exit 1
fi

# Prefer venv if present
if [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "[*] Kalshi Termux Portal"
echo "[*] Binding http://${HOST}:${PORT}"
echo "[*] Open on this device:"
echo "    http://127.0.0.1:${PORT}"

if command -v termux-open-url >/dev/null 2>&1; then
  termux-open-url "http://127.0.0.1:${PORT}" || true
else
  echo "[*] tip: termux-open-url http://127.0.0.1:${PORT}"
fi

# Fail clearly if port busy
if command -v ss >/dev/null 2>&1; then
  if ss -ltn 2>/dev/null | grep -q ":${PORT} "; then
    echo "[!] Port ${PORT} appears busy. Set PORT=8788 ./start.sh or kill the other process."
  fi
fi

exec python3 -m uvicorn app.main:app --host "$HOST" --port "$PORT" --log-level info
