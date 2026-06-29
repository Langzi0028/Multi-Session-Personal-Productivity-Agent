#!/usr/bin/env bash
set -euo pipefail

# Multi-Session Personal Productivity Agent launcher
#
# Usage:
#   ./start_all.sh start       # 后台启动，关闭终端不停止
#   ./start_all.sh stop        # 停止后端和前端
#   ./start_all.sh restart     # 重启
#   ./start_all.sh status      # 查看状态
#   ./start_all.sh logs        # 查看实时日志
#   ./start_all.sh foreground  # 前台启动，适合调试

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
VITE_PROXY_TARGET="${VITE_PROXY_TARGET:-http://127.0.0.1:${BACKEND_PORT}}"

PID_DIR="$ROOT_DIR/.run"
LOG_DIR="$ROOT_DIR/logs"

BACKEND_PID_FILE="$PID_DIR/backend.pid"
FRONTEND_PID_FILE="$PID_DIR/frontend.pid"

BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

cd "$ROOT_DIR"
mkdir -p "$PID_DIR" "$LOG_DIR"

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_CMD="$ROOT_DIR/.venv/bin/python"
else
  PYTHON_CMD="${PYTHON_CMD:-python3}"
fi

is_running() {
  local pid_file="$1"

  if [[ ! -f "$pid_file" ]]; then
    return 1
  fi

  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"

  if [[ -z "$pid" ]]; then
    return 1
  fi

  kill -0 "$pid" 2>/dev/null
}

check_ready() {
  if [[ ! -f "$ROOT_DIR/.env" ]]; then
    echo "ERROR: .env not found. Create .env first with your OPENAI_API_BASE / OPENAI_API_KEY / OPENAI_MODEL." >&2
    exit 1
  fi

  if ! "$PYTHON_CMD" -c "import fastapi, uvicorn, pydantic, httpx" >/dev/null 2>&1; then
    echo "ERROR: Python dependencies are not installed for: $PYTHON_CMD" >&2
    echo "Install them with:" >&2
    echo "  $PYTHON_CMD -m pip install -r requirements.txt" >&2
    exit 1
  fi

  if [[ ! -d "$ROOT_DIR/front-end/node_modules" ]]; then
    echo "ERROR: front-end/node_modules not found. Run once first:" >&2
    echo "  npm --prefix front-end install" >&2
    exit 1
  fi
}

start_backend() {
  if is_running "$BACKEND_PID_FILE"; then
    echo "Backend already running. PID=$(cat "$BACKEND_PID_FILE")"
    return
  fi

  echo "Starting backend: http://127.0.0.1:${BACKEND_PORT}"

  nohup setsid env \
    BACKEND_PORT="$BACKEND_PORT" \
    PYTHONUNBUFFERED=1 \
    "$PYTHON_CMD" "$ROOT_DIR/start_server.py" \
    >> "$BACKEND_LOG" 2>&1 &

  echo $! > "$BACKEND_PID_FILE"
  sleep 2

  if is_running "$BACKEND_PID_FILE"; then
    echo "Backend started. PID=$(cat "$BACKEND_PID_FILE")"
  else
    echo "ERROR: Backend failed to start. Check log:" >&2
    echo "  tail -n 100 $BACKEND_LOG" >&2
    rm -f "$BACKEND_PID_FILE"
    exit 1
  fi
}

start_frontend() {
  if is_running "$FRONTEND_PID_FILE"; then
    echo "Frontend already running. PID=$(cat "$FRONTEND_PID_FILE")"
    return
  fi

  echo "Starting frontend: http://${FRONTEND_HOST}:${FRONTEND_PORT}"

  nohup setsid bash -c '
    cd "$1/front-end"
    VITE_PROXY_TARGET="$2" exec npm run dev -- --host "$3" --port "$4"
  ' _ "$ROOT_DIR" "$VITE_PROXY_TARGET" "$FRONTEND_HOST" "$FRONTEND_PORT" \
    >> "$FRONTEND_LOG" 2>&1 &

  echo $! > "$FRONTEND_PID_FILE"
  sleep 2

  if is_running "$FRONTEND_PID_FILE"; then
    echo "Frontend started. PID=$(cat "$FRONTEND_PID_FILE")"
  else
    echo "ERROR: Frontend failed to start. Check log:" >&2
    echo "  tail -n 100 $FRONTEND_LOG" >&2
    rm -f "$FRONTEND_PID_FILE"
    exit 1
  fi
}

start_all() {
  check_ready
  start_backend
  start_frontend

  cat <<INFO

Started in background.
- Backend:          http://127.0.0.1:${BACKEND_PORT}
- Frontend:         http://${FRONTEND_HOST}:${FRONTEND_PORT}
- API proxy target: ${VITE_PROXY_TARGET}

Commands:
- View status:      ./start_all.sh status
- View logs:        ./start_all.sh logs
- Stop service:     ./start_all.sh stop
- Restart service:  ./start_all.sh restart
INFO
}

stop_one() {
  local name="$1"
  local pid_file="$2"

  if ! is_running "$pid_file"; then
    echo "$name is not running."
    rm -f "$pid_file"
    return
  fi

  local pid
  pid="$(cat "$pid_file")"

  echo "Stopping $name. PID=$pid"

  kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true

  for _ in {1..10}; do
    if kill -0 "$pid" 2>/dev/null; then
      sleep 1
    else
      break
    fi
  done

  if kill -0 "$pid" 2>/dev/null; then
    echo "$name did not stop gracefully. Force killing..."
    kill -KILL "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
  fi

  rm -f "$pid_file"
}

stop_all() {
  stop_one "frontend" "$FRONTEND_PID_FILE"
  stop_one "backend" "$BACKEND_PID_FILE"
}

show_one_status() {
  local name="$1"
  local pid_file="$2"

  if is_running "$pid_file"; then
    echo "$name: running, PID=$(cat "$pid_file")"
  else
    echo "$name: stopped"
  fi
}

status_all() {
  show_one_status "backend" "$BACKEND_PID_FILE"
  show_one_status "frontend" "$FRONTEND_PID_FILE"

  echo ""
  echo "Backend log:  $BACKEND_LOG"
  echo "Frontend log: $FRONTEND_LOG"
}

logs_all() {
  touch "$BACKEND_LOG" "$FRONTEND_LOG"
  tail -n 100 -f "$BACKEND_LOG" "$FRONTEND_LOG"
}

foreground_all() {
  check_ready

  cleanup() {
    echo ""
    echo "Stopping frontend/backend..."
    if [[ -n "${BACKEND_PID:-}" ]]; then
      kill "$BACKEND_PID" 2>/dev/null || true
    fi
    if [[ -n "${FRONTEND_PID:-}" ]]; then
      kill "$FRONTEND_PID" 2>/dev/null || true
    fi
  }

  trap cleanup EXIT INT TERM

  echo "Starting backend with $PYTHON_CMD: http://127.0.0.1:${BACKEND_PORT}"
  BACKEND_PORT="$BACKEND_PORT" PYTHONUNBUFFERED=1 "$PYTHON_CMD" "$ROOT_DIR/start_server.py" &
  BACKEND_PID=$!

  sleep 2

  echo "Starting frontend: http://${FRONTEND_HOST}:${FRONTEND_PORT}"
  cd "$ROOT_DIR/front-end"
  VITE_PROXY_TARGET="$VITE_PROXY_TARGET" npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" &
  FRONTEND_PID=$!

  cat <<INFO

Started in foreground.
- Backend:          http://127.0.0.1:${BACKEND_PORT}
- Frontend:         http://${FRONTEND_HOST}:${FRONTEND_PORT}
- API proxy target: ${VITE_PROXY_TARGET}

Press Ctrl+C to stop both.
INFO

  wait
}

case "${1:-start}" in
  start)
    start_all
    ;;
  stop)
    stop_all
    ;;
  restart)
    stop_all
    sleep 1
    start_all
    ;;
  status)
    status_all
    ;;
  logs)
    logs_all
    ;;
  foreground)
    foreground_all
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|logs|foreground}"
    exit 1
    ;;
esac