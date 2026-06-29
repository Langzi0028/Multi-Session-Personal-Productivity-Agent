from fastapi.testclient import TestClient

from api_auth_helpers import create_authenticated_session
from app.contracts import MessageRole
from app.llm.fake import ScriptedLLM
from app.main import app, build_default_runtime


def test_manual_runtime_executes_tool_calls_and_persists_todo():
    runtime = build_default_runtime([
        {
            "type": "tool_call",
            "thought_summary": "查询天气",
            "tool_name": "weather",
            "arguments": {"city": "北京"},
        },
        {
            "type": "tool_call",
            "thought_summary": "添加待办",
            "tool_name": "todo",
            "arguments": {"action": "add", "content": "晚上 8 点带伞出门"},
        },
        {
            "type": "final",
            "thought_summary": "完成",
            "answer": "北京今天多云，下午可能有阵雨。已记录待办：晚上 8 点带伞出门。",
        },
    ])

    result = runtime.handle_user_message(
        "user_A",
        "window_1",
        "北京今天天气怎么样？顺便帮我记一个待办：晚上 8 点带伞出门。",
    )

    assert "北京今天多云" in result.answer
    assert [todo.content for todo in runtime.session_manager.list_todos("user_A", "window_1")] == ["晚上 8 点带伞出门"]
    traces = runtime.trace_logger.list_traces("user_A", "window_1")
    assert [(trace.action_type, trace.tool_name) for trace in traces] == [
        ("tool_call", "weather"),
        ("tool_result", "weather"),
        ("tool_call", "todo"),
        ("tool_result", "todo"),
        ("final", None),
    ]
    state = runtime.session_manager.get_state("user_A", "window_1")
    assert [message.role for message in state.messages] == [
        MessageRole.USER,
        MessageRole.TOOL,
        MessageRole.TOOL,
        MessageRole.ASSISTANT,
    ]
    assert isinstance(runtime.llm_client, ScriptedLLM)
    assert not hasattr(runtime, "graph")


def test_manual_runtime_keeps_user_and_session_todos_isolated():
    runtime = build_default_runtime([
        {
            "type": "tool_call",
            "thought_summary": "添加 window_1 待办",
            "tool_name": "todo",
            "arguments": {"action": "add", "content": "晚上 8 点带伞出门"},
        },
        {"type": "final", "thought_summary": "完成", "answer": "window_1 done"},
        {
            "type": "tool_call",
            "thought_summary": "添加 window_2 待办",
            "tool_name": "todo",
            "arguments": {"action": "add", "content": "明天上午整理 README"},
        },
        {"type": "final", "thought_summary": "完成", "answer": "window_2 done"},
        {
            "type": "tool_call",
            "thought_summary": "添加 user_B 待办",
            "tool_name": "todo",
            "arguments": {"action": "add", "content": "user_B 私有待办"},
        },
        {"type": "final", "thought_summary": "完成", "answer": "user_B done"},
    ])

    runtime.handle_user_message("user_A", "window_1", "添加带伞待办")
    runtime.handle_user_message("user_A", "window_2", "添加 README 待办")
    runtime.handle_user_message("user_B", "window_1", "添加私有待办")

    assert [todo.content for todo in runtime.session_manager.list_todos("user_A", "window_1")] == ["晚上 8 点带伞出门"]
    assert [todo.content for todo in runtime.session_manager.list_todos("user_A", "window_2")] == ["明天上午整理 README"]
    assert [todo.content for todo in runtime.session_manager.list_todos("user_B", "window_1")] == ["user_B 私有待办"]


def test_message_api_returns_todos_after_manual_tool_call_flow():
    runtime = build_default_runtime([
        {
            "type": "tool_call",
            "thought_summary": "添加待办",
            "tool_name": "todo",
            "arguments": {"action": "add", "content": "晚上 8 点带伞出门"},
        },
        {"type": "final", "thought_summary": "完成", "answer": "已记录待办：晚上 8 点带伞出门。"},
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
        json={"content": "帮我记一个待办：晚上 8 点带伞出门。"},
    )

    assert response.status_code == 200
    assert "无法" not in response.json()["answer"]
    todos = client.get(f"/sessions/{session_id}/todos", headers=headers).json()["todos"]
    assert [todo["content"] for todo in todos] == ["晚上 8 点带伞出门"]
