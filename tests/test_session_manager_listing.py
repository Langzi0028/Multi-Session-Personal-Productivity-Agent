from app.contracts import MessageRole, SessionStatus
from app.runtime.session_manager import SessionManager
from app.storage.sqlite_store import SQLiteStore


def build_manager() -> SessionManager:
    store = SQLiteStore(":memory:")
    store.init_schema()
    return SessionManager(store)


def insert_session(manager: SessionManager, user_id: str, session_id: str, updated_at: str) -> None:
    manager.store.execute(
        """
        INSERT INTO sessions (user_id, session_id, status, summary, created_at, updated_at)
        VALUES (?, ?, ?, '', ?, ?)
        """,
        (user_id, session_id, SessionStatus.IDLE.value, updated_at, updated_at),
    )


def test_list_sessions_is_user_scoped_and_ordered_by_recent_update():
    manager = build_manager()
    insert_session(manager, "user_A", "older", "2026-06-28T09:00:00+00:00")
    insert_session(manager, "user_A", "newer", "2026-06-28T10:00:00+00:00")
    insert_session(manager, "user_B", "private", "2026-06-28T11:00:00+00:00")

    sessions = manager.list_sessions("user_A")

    assert [session.session_id for session in sessions] == ["newer", "older"]
    assert all(session.user_id == "user_A" for session in sessions)


def test_session_summary_includes_visible_message_preview_and_count():
    manager = build_manager()
    insert_session(manager, "user_A", "window_1", "2026-06-28T09:00:00+00:00")
    manager.add_message("user_A", "window_1", MessageRole.USER, "帮我查北京天气")
    manager.add_message("user_A", "window_1", MessageRole.TOOL, "weather result")
    manager.add_message("user_A", "window_1", MessageRole.ASSISTANT, "北京今天多云，下午可能有阵雨。")

    summary = manager.get_session_summary("user_A", "window_1")

    assert summary is not None
    assert summary.last_message_preview == "北京今天多云，下午可能有阵雨。"
    assert summary.message_count == 2


def test_list_messages_returns_visible_chat_messages_only():
    manager = build_manager()
    insert_session(manager, "user_A", "window_1", "2026-06-28T09:00:00+00:00")
    manager.add_message("user_A", "window_1", MessageRole.USER, "你好")
    manager.add_message("user_A", "window_1", MessageRole.TOOL, "hidden tool output")
    manager.add_message("user_A", "window_1", MessageRole.ASSISTANT, "你好，有什么可以帮你？")

    messages = manager.list_messages("user_A", "window_1")

    assert [message.role for message in messages] == [MessageRole.USER, MessageRole.ASSISTANT]
    assert [message.content for message in messages] == ["你好", "你好，有什么可以帮你？"]
