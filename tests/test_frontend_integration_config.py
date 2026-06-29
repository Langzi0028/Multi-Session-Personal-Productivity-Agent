from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "front-end"


def test_frontend_api_client_uses_vite_api_base_without_hardcoded_backend_origin():
    app_source = (FRONTEND / "src" / "app" / "App.tsx").read_text(encoding="utf-8")

    assert "import.meta.env.VITE_API_BASE" in app_source
    assert '"/api"' in app_source or "'/api'" in app_source
    assert "http://localhost:8000" not in app_source
    assert "http://127.0.0.1:8000" not in app_source


def test_vite_dev_server_proxies_api_requests_to_fastapi_backend():
    vite_config = (FRONTEND / "vite.config.ts").read_text(encoding="utf-8")

    assert "server:" in vite_config
    assert "'/api'" in vite_config or '"/api"' in vite_config
    assert "process.env.VITE_PROXY_TARGET" in vite_config
    assert "http://127.0.0.1:8000" in vite_config
    assert "rewrite:" in vite_config
    assert "replace(/^/api" not in vite_config
    assert "replace(/^\\/api" in vite_config


def test_frontend_declares_runtime_and_typecheck_dependencies():
    package_json = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))

    dependencies = package_json["dependencies"]
    dev_dependencies = package_json["devDependencies"]

    assert dependencies["react"] == "18.3.1"
    assert dependencies["react-dom"] == "18.3.1"
    assert "typecheck" in package_json["scripts"]
    assert "typescript" in dev_dependencies
    assert "@types/react" in dev_dependencies
    assert "@types/react-dom" in dev_dependencies
    assert "@types/node" in dev_dependencies


def test_frontend_has_vite_env_types_for_import_meta_env():
    vite_env = FRONTEND / "src" / "vite-env.d.ts"

    assert vite_env.exists()
    assert "vite/client" in vite_env.read_text(encoding="utf-8")


def test_frontend_uses_auth_and_owned_session_list_instead_of_demo_controls():
    app_source = (FRONTEND / "src" / "app" / "App.tsx").read_text(encoding="utf-8")

    assert "/auth/login" in app_source
    assert "/auth/register" in app_source
    assert "Authorization" in app_source
    assert 'apiFetch("/sessions"' in app_source or "apiFetch('/sessions'" in app_source
    assert "演示切换" not in app_source
    assert "API Base" not in app_source
    assert "Session 控制" not in app_source


def test_frontend_preserves_backend_trace_order_across_turns():
    app_source = (FRONTEND / "src" / "app" / "App.tsx").read_text(encoding="utf-8")

    assert "sort((a, b) => a.step - b.step)" not in app_source
    assert "setTraces(traceData.traces ?? [])" in app_source


def test_frontend_persists_active_session_and_scopes_sending_state():
    app_source = (FRONTEND / "src" / "app" / "App.tsx").read_text(encoding="utf-8")

    assert "ACTIVE_SESSION_KEY" in app_source
    assert "localStorage.setItem(ACTIVE_SESSION_KEY" in app_source
    assert "localStorage.getItem(ACTIVE_SESSION_KEY)" in app_source
    assert "sendingSessionIds" in app_source
    assert "const currentSessionSending =" in app_source
    assert "disabled={currentSessionSending}" in app_source
    assert "disabled={!input.trim() || currentSessionSending}" in app_source
    assert "disabled={sending}" not in app_source


def test_frontend_restores_running_session_loading_after_refresh():
    app_source = (FRONTEND / "src" / "app" / "App.tsx").read_text(encoding="utf-8")

    assert "isSessionRunning" in app_source
    assert "restoreRunningSessionLoading" in app_source
    assert "Agent 正在运行…" in app_source
    assert "setSendingSessionIds" in app_source
    assert "next.add(sessionId)" in app_source


def test_frontend_polls_restored_running_session_until_completion():
    app_source = (FRONTEND / "src" / "app" / "App.tsx").read_text(encoding="utf-8")

    assert "window.setInterval" in app_source
    assert "pollRunningSession" in app_source
    assert "loadSession(sessionId, session)" in app_source
    assert "next.delete(sessionId)" in app_source
