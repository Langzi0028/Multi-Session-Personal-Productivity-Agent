from fastapi.testclient import TestClient

from api_auth_helpers import register_and_auth
from app.demo_runtime import build_manual_demo_runtime
from app.main import app


def test_manual_demo_runtime_matches_manual_test_flow():
    runtime = build_manual_demo_runtime()
    app.state.runtime = runtime
    app.state.session_manager = runtime.session_manager
    app.state.trace_logger = runtime.trace_logger
    app.state.auth_manager = runtime.auth_manager
    client = TestClient(app)
    headers = register_and_auth(client)

    session_1 = client.post("/sessions", headers=headers).json()["session"]["session_id"]
    session_2 = client.post("/sessions", headers=headers).json()["session"]["session_id"]

    window_1 = client.post(
        f"/sessions/{session_1}/messages",
        headers=headers,
        json={"content": "北京今天天气怎么样？顺便帮我记一个待办：晚上 8 点带伞出门。"},
    )
    assert "北京今天多云" in window_1.json()["answer"]

    window_2 = client.post(
        f"/sessions/{session_2}/messages",
        headers=headers,
        json={"content": "帮我记一个待办：明天上午整理 README。"},
    )
    assert "README" in window_2.json()["answer"]

    todos_1 = client.get(f"/sessions/{session_1}/todos", headers=headers).json()["todos"]
    todos_2 = client.get(f"/sessions/{session_2}/todos", headers=headers).json()["todos"]
    assert [todo["content"] for todo in todos_1] == ["晚上 8 点带伞出门"]
    assert [todo["content"] for todo in todos_2] == ["明天上午整理 README"]

    traces_1 = client.get(f"/sessions/{session_1}/trace", headers=headers).json()["traces"]
    assert [trace["action_type"] for trace in traces_1] == [
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
        "final",
    ]

    sessions = client.get("/sessions", headers=headers).json()["sessions"]
    assert {session["session_id"] for session in sessions} == {session_1, session_2}
