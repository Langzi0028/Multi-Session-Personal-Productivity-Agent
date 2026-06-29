from fastapi.testclient import TestClient

from app.main import app, build_default_runtime


def make_client() -> TestClient:
    runtime = build_default_runtime()
    app.state.runtime = runtime
    app.state.session_manager = runtime.session_manager
    app.state.trace_logger = runtime.trace_logger
    app.state.auth_manager = runtime.auth_manager
    return TestClient(app)


def test_register_login_me_and_logout_flow():
    client = make_client()

    register = client.post("/auth/register", json={"username": "Alice", "password": "password123"})
    assert register.status_code == 201
    payload = register.json()
    assert payload["token_type"] == "bearer"
    assert payload["token"]
    assert payload["user"]["username"] == "alice"

    duplicate = client.post("/auth/register", json={"username": "alice", "password": "password456"})
    assert duplicate.status_code == 409

    bad_login = client.post("/auth/login", json={"username": "alice", "password": "wrong-password"})
    assert bad_login.status_code == 401

    login = client.post("/auth/login", json={"username": "alice", "password": "password123"})
    assert login.status_code == 200
    token = login.json()["token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["user"]["username"] == "alice"

    logout = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout.status_code == 200
    assert logout.json() == {"status": "ok"}

    after_logout = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert after_logout.status_code == 401


def test_protected_sessions_require_bearer_token():
    client = make_client()

    response = client.get("/sessions")

    assert response.status_code == 401
