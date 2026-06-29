#!/usr/bin/env bash
set -euo pipefail

# CentOS + Caddy one-click deploy script for this project.
# Usage after git clone:
#   cd /opt/bishi
#   chmod +x deploy_centos_caddy.sh
#   ./deploy_centos_caddy.sh
#
# Optional env vars:
#   DOMAIN=example.com ./deploy_centos_caddy.sh
#   APP_DIR=/opt/bishi BACKEND_PORT=8000 DOMAIN=example.com ./deploy_centos_caddy.sh

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
APP_USER="${APP_USER:-$(whoami)}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
SERVICE_NAME="${SERVICE_NAME:-bishi-backend}"
DOMAIN="${DOMAIN:-}"
CADDYFILE="${CADDYFILE:-/etc/caddy/Caddyfile}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$APP_DIR"

echo "==> App dir: $APP_DIR"
echo "==> App user: $APP_USER"
echo "==> Backend: $BACKEND_HOST:$BACKEND_PORT"

install_system_packages() {
  if command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y git python3 python3-pip nodejs npm
  elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y epel-release || true
    sudo yum install -y git python3 python3-pip nodejs npm
  else
    echo "ERROR: neither yum nor dnf found. Install git/python3/nodejs/npm manually." >&2
    exit 1
  fi
}

ensure_python_pip() {
  if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
    echo "==> pip not found, trying ensurepip"
    "$PYTHON_BIN" -m ensurepip --upgrade || true
  fi
  if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
    echo "ERROR: python pip is still unavailable. Try: sudo yum install -y python3-pip" >&2
    exit 1
  fi
}

ensure_env_file() {
  if [[ -f "$APP_DIR/.env" ]]; then
    return
  fi

  cat > "$APP_DIR/.env.example.server" <<'EOF'
OPENAI_API_BASE=https://your-openai-compatible-api-base/v1
OPENAI_API_KEY=replace-with-your-real-key-on-server
OPENAI_MODEL=replace-with-your-model-name

SQLITE_DB_PATH=/opt/bishi/data/agent_runtime.db
VECTOR_STORE_PATH=/opt/bishi/data/vector_store

MAX_AGENT_STEPS=5

MEMORY_EXTRACTOR_MODE=llm
MEMORY_EXTRACTOR_TIMEOUT_SECONDS=10
MEMORY_EXTRACTOR_MODEL=
MEMORY_EXTRACTOR_MAX_INPUT_CHARS=6000
EOF

  echo "ERROR: .env not found."
  echo "A template was created at: $APP_DIR/.env.example.server"
  echo "Copy it to .env and fill in your real server-only API config:"
  echo "  cp $APP_DIR/.env.example.server $APP_DIR/.env"
  echo "  nano $APP_DIR/.env"
  echo "Then re-run this script."
  exit 1
}

setup_backend() {
  echo "==> Setting up backend"
  mkdir -p "$APP_DIR/data"

  if [[ ! -d "$APP_DIR/.venv" ]]; then
    "$PYTHON_BIN" -m venv "$APP_DIR/.venv"
  fi

  "$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
  "$APP_DIR/.venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt"
}

setup_frontend() {
  echo "==> Building frontend"
  cd "$APP_DIR/front-end"
  npm install
  npm run build
  cd "$APP_DIR"
}

write_systemd_service() {
  echo "==> Writing systemd service: $SERVICE_NAME"
  sudo tee "/etc/systemd/system/${SERVICE_NAME}.service" >/dev/null <<EOF
[Unit]
Description=Bishi FastAPI Backend
After=network.target

[Service]
User=$APP_USER
WorkingDirectory=$APP_DIR
Environment="PYTHONUNBUFFERED=1"
ExecStart=$APP_DIR/.venv/bin/python $APP_DIR/start_server.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

  sudo systemctl daemon-reload
  sudo systemctl enable "$SERVICE_NAME"
  sudo systemctl restart "$SERVICE_NAME"
}

write_caddyfile_if_requested() {
  if [[ -z "$DOMAIN" ]]; then
    echo "==> DOMAIN not set; skipping Caddyfile write."
    echo "    If you want this script to write Caddy config, run:"
    echo "    DOMAIN=example.com ./deploy_centos_caddy.sh"
    return
  fi

  if ! command -v caddy >/dev/null 2>&1; then
    echo "ERROR: caddy command not found. Install Caddy first, then re-run with DOMAIN=$DOMAIN." >&2
    exit 1
  fi

  echo "==> Writing Caddyfile for domain: $DOMAIN"
  sudo mkdir -p "$(dirname "$CADDYFILE")"
  sudo tee "$CADDYFILE" >/dev/null <<EOF
$DOMAIN {
    root * $APP_DIR/front-end/dist

    handle /api/* {
        uri strip_prefix /api
        reverse_proxy $BACKEND_HOST:$BACKEND_PORT
    }

    handle {
        try_files {path} /index.html
        file_server
    }
}
EOF

  sudo caddy validate --config "$CADDYFILE"
  sudo systemctl enable caddy
  sudo systemctl reload caddy || sudo systemctl restart caddy
}

health_check() {
  echo "==> Checking backend health"
  sleep 2
  if curl -fsS "http://$BACKEND_HOST:$BACKEND_PORT/health" >/dev/null; then
    echo "Backend OK: http://$BACKEND_HOST:$BACKEND_PORT/health"
  else
    echo "WARNING: backend health check failed. Check logs: journalctl -u $SERVICE_NAME -f" >&2
  fi
}

install_system_packages
ensure_python_pip
ensure_env_file
setup_backend
setup_frontend
write_systemd_service
write_caddyfile_if_requested
health_check

echo ""
echo "==> Done."
echo "Backend service: sudo systemctl status $SERVICE_NAME"
echo "Backend logs:    journalctl -u $SERVICE_NAME -f"
if [[ -n "$DOMAIN" ]]; then
  echo "Frontend URL:    https://$DOMAIN"
  echo "API health:      https://$DOMAIN/api/health"
else
  echo "Frontend built:  $APP_DIR/front-end/dist"
  echo "Caddy config was not changed because DOMAIN was empty."
fi
