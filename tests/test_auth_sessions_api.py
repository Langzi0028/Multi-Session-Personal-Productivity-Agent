from fastapi.testclient import TestClient

from app.main import app, build_default_runtime


def make_client(scripted_responses=None) -> TestClient:
    runtime = build_default_runtime(scripted_responses or [])
    app.state.runtime = runtime
    app.state.session_manager = runtime.session_manager
    app.state.trace_logger = runtime.trace_logger
    app.state.auth_manager = runtime.auth_manager
    return TestClient(app)


def auth_headers(client: TestClient, username: str) -> dict[str, str]:
    response = client.post("/auth/register", json={"username": username, "password": "password123"})
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_users_only_see_their_own_sessions():
    client = make_client()
    alice = auth_headers(client, "alice")
    bob = auth_headers(client, "bob")

    alice_session = client.post("/sessions", headers=alice).json()["session"]
    bob_session = client.post("/sessions", headers=bob).json()["session"]

    alice_sessions = client.get("/sessions", headers=alice).json()["sessions"]
    bob_sessions = client.get("/sessions", headers=bob).json()["sessions"]

    assert [session["session_id"] for session in alice_sessions] == [alice_session["session_id"]]
    assert [session["session_id"] for session in bob_sessions] == [bob_session["session_id"]]


def test_message_todo_trace_and_history_use_authenticated_user_not_user_id_payload():
    client = make_client([
        {
            "type": "tool_call",
            "thought_summary": "添加待办",
            "tool_name": "todo",
            "arguments": {"action": "add", "content": "晚上 8 点带伞出门"},
        },
        {"type": "final", "thought_summary": "完成", "answer": "已记录待办：晚上 8 点带伞出门。"},
    ])
    alice = auth_headers(client, "alice")
    bob = auth_headers(client, "bob")
    session_id = client.post("/sessions", headers=alice).json()["session"]["session_id"]

    response = client.post(
        f"/sessions/{session_id}/messages",
        headers=alice,
        json={"content": "帮我记一个待办：晚上 8 点带伞出门。", "user_id": "bob"},
    )

    assert response.status_code == 200
    assert "已记录待办" in response.json()["answer"]

    todos = client.get(f"/sessions/{session_id}/todos", headers=alice).json()["todos"]
    assert [todo["content"] for todo in todos] == ["晚上 8 点带伞出门"]

    traces = client.get(f"/sessions/{session_id}/trace", headers=alice).json()["traces"]
    assert [trace["action_type"] for trace in traces] == ["tool_call", "tool_result", "final"]

    messages = client.get(f"/sessions/{session_id}/messages", headers=alice).json()["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[0]["content"].startswith("帮我记一个待办")

    assert client.get(f"/sessions/{session_id}/messages", headers=bob).status_code == 404
    assert client.get(f"/sessions/{session_id}/todos", headers=bob).status_code == 404
    assert client.get(f"/sessions/{session_id}/trace", headers=bob).status_code == 404
