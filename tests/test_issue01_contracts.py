from pathlib import Path

from fastapi import FastAPI

from app.contracts import (
    AsyncJobStatus,
    ErrorCode,
    FinalAction,
    LLMActionType,
    SessionState,
    SessionStatus,
    TodoStatus,
    ToolCallAction,
)
from app.main import app
from app.storage.sqlite_store import SQLiteStore


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_project_contract_files_exist():
    requirements_text = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "chromadb" in requirements_text
    env_example = PROJECT_ROOT / "env.example"
    assert env_example.exists()
    env_text = env_example.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY" in env_text
    assert "VECTOR_STORE_PATH" in env_text
    assert "MEMORY_EXTRACTOR_MODE" in env_text
    assert "sk-" not in env_text


def test_fastapi_app_is_importable():
    assert isinstance(app, FastAPI)


def test_core_llm_action_contracts_validate_literals():
    final = FinalAction(type="final", thought_summary="ready", answer="hello")
    assert final.type == LLMActionType.FINAL
    assert final.answer == "hello"

    tool_call = ToolCallAction(
        type="tool_call",
        thought_summary="need weather",
        tool_name="weather",
        arguments={"city": "北京"},
    )
    assert tool_call.type == LLMActionType.TOOL_CALL
    assert tool_call.arguments == {"city": "北京"}


def test_session_state_and_enums_are_fixed():
    state = SessionState(user_id="user_A", session_id="window_1")
    assert state.status == SessionStatus.IDLE
    assert state.messages == []
    assert state.todos == []
    assert TodoStatus.PENDING.value == "pending"
    assert AsyncJobStatus.SUBMITTED.value == "submitted"
    assert ErrorCode.MAX_STEPS_EXCEEDED.value == "MAX_STEPS_EXCEEDED"


def test_sqlite_schema_initializes_core_tables():
    store = SQLiteStore(":memory:")
    store.init_schema()

    table_names = set(store.list_table_names())
    assert {
        "sessions",
        "messages",
        "todos",
        "tool_traces",
        "async_jobs",
        "users",
        "auth_tokens",
        "user_profiles",
        "user_profile_facts",
        "semantic_memories",
        "episodic_memories",
    }.issubset(table_names)
