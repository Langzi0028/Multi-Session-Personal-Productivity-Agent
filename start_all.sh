#!/usr/bin/env bash
set -euo pipefail

# One-command local/server dev start for backend + frontend.
# Usage:
#   chmod +x start_all.sh
#   ./start_all.sh
#
# Optional:
#   BACKEND_PORT=8000 FRONTEND_PORT=5173 ./start_all.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
VITE_PROXY_TARGET="${VITE_PROXY_TARGET:-http://127.0.0.1:${BACKEND_PORT}}"

cd "$ROOT_DIR"

if [[ ! -f ".env" ]]; then
  echo "ERROR: .env not found. Create .env first with your OPENAI_API_BASE / OPENAI_API_KEY / OPENAI_MODEL." >&2
  exit 1
fi

if [[ ! -d ".venv" ]]; then
  echo "ERROR: .venv not found. Run these once first:" >&2
  echo "  python3 -m venv .venv" >&2
  echo "  source .venv/bin/activate" >&2
  echo "  python -m pip install -r requirements.txt" >&2
  exit 1
fi

if [[ ! -d "front-end/node_modules" ]]; then
  echo "ERROR: front-end/node_modules not found. Run once first:" >&2
  echo "  npm --prefix front-end install" >&2
  exit 1
fi

cleanup() {
  echo ""
  echo "Stopping frontend/backend..."
  if [[ -n "${BACKEND_PID:-}" ]]; then kill "$BACKEND_PID" 2>/dev/null || true; fi
  if [[ -n "${FRONTEND_PID:-}" ]]; then kill "$FRONTEND_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM

echo "Starting backend: http://127.0.0.1:${BACKEND_PORT}"
"$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/start_server.py" &
BACKEND_PID=$!

sleep 2

echo "Starting frontend: http://${FRONTEND_HOST}:${FRONTEND_PORT}"
cd "$ROOT_DIR/front-end"
VITE_PROXY_TARGET="$VITE_PROXY_TARGET" npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" &
FRONTEND_PID=$!

cat <<EOF

Started.
- Backend:  http://127.0.0.1:${BACKEND_PORT}
- Frontend: http://${FRONTEND_HOST}:${FRONTEND_PORT}
- API proxy target: ${VITE_PROXY_TARGET}

Press Ctrl+C to stop both.
EOF

wait
