from fastapi.testclient import TestClient

from api_auth_helpers import create_authenticated_session
from app.main import app, build_default_runtime


def test_json_response_declares_utf8_charset():
    runtime = build_default_runtime([
        {"type": "final", "thought_summary": "ok", "answer": "北京中文响应"},
    ])
    app.state.runtime = runtime
    app.state.session_manager = runtime.session_manager
    app.state.trace_logger = runtime.trace_logger
    app.state.auth_manager = runtime.auth_manager
    client = TestClient(app)
    headers, session_id = create_authenticated_session(client)

    response = client.post(
        f"/sessions/{session_id}/messages",
        headers=headers,
        json={"content": "你好"},
    )

    assert response.status_code == 200
    assert "charset=utf-8" in response.headers["content-type"].lower()
    assert response.json()["answer"] == "北京中文响应"
