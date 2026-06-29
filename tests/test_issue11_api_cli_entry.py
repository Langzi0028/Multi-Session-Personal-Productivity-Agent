from fastapi.testclient import TestClient

from api_auth_helpers import create_authenticated_session
from app.config import Settings
from app.main import app, build_default_runtime
from app.memory.extractor import HeuristicMemoryExtractor, LLMMemoryExtractor
from app.memory.manager import MemoryManager


def test_default_runtime_wires_memory_manager():
    runtime = build_default_runtime()

    assert isinstance(runtime.memory_manager, MemoryManager)
    assert runtime.context_manager.memory_manager is runtime.memory_manager
    assert isinstance(runtime.memory_manager.extractor, HeuristicMemoryExtractor)


def test_real_runtime_wires_llm_memory_extractor_when_enabled():
    settings = Settings(
        openai_api_base="https://api.example.test",
        openai_api_key="secret-value",
        openai_model="action-model",
        sqlite_db_path=":memory:",
        vector_store_path="./test_vector_store",
        max_agent_steps=3,
        memory_extractor_mode="llm",
        memory_extractor_timeout_seconds=4.5,
        memory_extractor_model="memory-model",
        memory_extractor_max_input_chars=1234,
    )

    runtime = build_default_runtime(use_real_llm=True, settings=settings, enable_vector_store=False)

    assert isinstance(runtime.memory_manager.extractor, LLMMemoryExtractor)
    assert runtime.memory_manager.extractor.json_client is runtime.llm_client


def test_fastapi_session_message_todo_and_trace_flow():
    runtime = build_default_runtime([
        {
            "type": "tool_call",
            "thought_summary": "need weather",
            "tool_name": "weather",
            "arguments": {"city": "北京"},
        },
        {
            "type": "tool_call",
            "thought_summary": "need todo",
            "tool_name": "todo",
            "arguments": {"action": "add", "content": "晚上 8 点带伞出门"},
        },
        {
            "type": "final",
            "thought_summary": "done",
            "answer": "北京今天多云，下午可能有阵雨。已记录待办：晚上 8 点带伞出门。",
        },
    ])
    app.state.runtime = runtime
    app.state.session_manager = runtime.session_manager
    app.state.trace_logger = runtime.trace_logger
    app.state.auth_manager = runtime.auth_manager
    client = TestClient(app)
    headers, session_id = create_authenticated_session(client)

    message_response = client.post(
        f"/sessions/{session_id}/messages",
        headers=headers,
        json={"content": "北京今天天气怎么样？顺便帮我记一个待办：晚上 8 点带伞出门。"},
    )
    assert message_response.status_code == 200
    assert "北京今天多云" in message_response.json()["answer"]

    todos_response = client.get(f"/sessions/{session_id}/todos", headers=headers)
    assert todos_response.status_code == 200
    assert todos_response.json()["todos"][0]["content"] == "晚上 8 点带伞出门"

    trace_response = client.get(f"/sessions/{session_id}/trace", headers=headers)
    assert trace_response.status_code == 200
    assert [trace["action_type"] for trace in trace_response.json()["traces"]] == [
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
        "final",
    ]

    sessions_response = client.get("/sessions", headers=headers)
    assert sessions_response.status_code == 200
    assert sessions_response.json()["sessions"][0]["session_id"] == session_id
