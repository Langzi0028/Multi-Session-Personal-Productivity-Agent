from app.contracts import MessageRole
from app.runtime.context_manager import ContextManager
from app.runtime.session_manager import SessionManager
from app.storage.sqlite_store import SQLiteStore


def test_context_contains_current_session_recent_messages_tool_results_and_todos_only():
    store = SQLiteStore(":memory:")
    store.init_schema()
    session_manager = SessionManager(store)
    context_manager = ContextManager(session_manager)

    session_manager.add_message("user_A", "window_1", MessageRole.USER, "北京天气怎么样？")
    session_manager.add_message("user_A", "window_1", MessageRole.TOOL, "北京今天多云，下午可能有阵雨。")
    session_manager.add_todo("user_A", "window_1", "晚上 8 点带伞出门")
    session_manager.add_message("user_A", "window_2", MessageRole.TOOL, "上海今天晴朗。")
    session_manager.add_todo("user_A", "window_2", "明天上午整理 README")

    context = context_manager.build_context("user_A", "window_1", "那我晚上要带伞吗？")
    context_text = "\n".join(str(item) for item in context)

    assert "北京今天多云" in context_text
    assert "晚上 8 点带伞出门" in context_text
    assert "那我晚上要带伞吗" in context_text
    assert "上海今天晴朗" not in context_text
    assert "明天上午整理 README" not in context_text


def test_context_limits_recent_messages():
    store = SQLiteStore(":memory:")
    store.init_schema()
    session_manager = SessionManager(store)
    context_manager = ContextManager(session_manager, recent_message_limit=3)

    for index in range(6):
        session_manager.add_message("user_A", "window_1", MessageRole.USER, f"message-{index}")

    context = context_manager.build_context("user_A", "window_1", "current")
    context_text = "\n".join(str(item) for item in context)

    assert "message-0" not in context_text
    assert "message-1" not in context_text
    assert "message-3" in context_text
    assert "message-4" in context_text
    assert "message-5" in context_text
