from app.contracts import MessageRole
from app.runtime.context_manager import ContextManager
from app.runtime.session_manager import SessionManager
from app.storage.sqlite_store import SQLiteStore


def test_compress_old_messages_updates_summary_and_keeps_recent_messages_and_todos():
    store = SQLiteStore(":memory:")
    store.init_schema()
    session_manager = SessionManager(store)
    context_manager = ContextManager(session_manager, recent_message_limit=4)

    for index in range(8):
        session_manager.add_message("user_A", "window_1", MessageRole.USER, f"old-message-{index}")
    session_manager.add_message("user_A", "window_1", MessageRole.TOOL, "关键工具结果：北京下午可能有阵雨。")
    session_manager.add_todo("user_A", "window_1", "晚上 8 点带伞出门")

    compressed = context_manager.compress_if_needed("user_A", "window_1", max_message_count=6)

    assert compressed is True
    state = session_manager.get_state("user_A", "window_1")
    assert "old-message-0" in state.session_summary
    assert "old-message-4" in state.session_summary
    assert [todo.content for todo in state.todos] == ["晚上 8 点带伞出门"]

    context = context_manager.build_context("user_A", "window_1", "晚上还要带伞吗？")
    context_text = "\n".join(str(item) for item in context)
    assert "old-message-0" in context_text
    assert "old-message-7" in context_text
    assert "关键工具结果：北京下午可能有阵雨。" in context_text
    assert "晚上 8 点带伞出门" in context_text


def test_compress_not_triggered_when_under_threshold():
    store = SQLiteStore(":memory:")
    store.init_schema()
    session_manager = SessionManager(store)
    context_manager = ContextManager(session_manager)
    session_manager.add_message("user_A", "window_1", MessageRole.USER, "hello")

    compressed = context_manager.compress_if_needed("user_A", "window_1", max_message_count=6)

    assert compressed is False
    assert session_manager.get_state("user_A", "window_1").session_summary == ""
