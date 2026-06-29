from app.memory.manager import MemoryManager
from app.runtime.context_manager import ContextManager
from app.runtime.session_manager import SessionManager
from app.storage.sqlite_store import SQLiteStore


def test_long_term_memory_recall_filters_by_user_id():
    store = SQLiteStore(":memory:")
    store.init_schema()
    memory = MemoryManager(store)

    memory.upsert_profile("user_A", preferred_language="中文", answer_style="直接")
    memory.add_semantic_memory("user_A", "用户正在准备 Agent 开发岗笔试。", source_session_id="window_1")
    memory.add_episodic_memory("user_A", "window_1", "todo_added", "添加了晚上 8 点带伞出门的待办。")
    memory.add_semantic_memory("user_B", "用户喜欢英文回答。", source_session_id="window_9")

    recalled = memory.retrieve("user_A", "之前我让你记了什么？")
    recalled_text = "\n".join(item["content"] for item in recalled)

    assert "Agent 开发岗笔试" in recalled_text
    assert "带伞" in recalled_text
    assert "英文回答" not in recalled_text


def test_context_includes_recalled_long_term_memory():
    store = SQLiteStore(":memory:")
    store.init_schema()
    session_manager = SessionManager(store)
    memory = MemoryManager(store)
    memory.upsert_profile("user_A", preferred_language="中文", answer_style="直接")
    memory.add_semantic_memory("user_A", "用户偏好中文解释技术方案。")
    context_manager = ContextManager(session_manager, memory_manager=memory)

    context = context_manager.build_context("user_A", "window_1", "继续完善之前的 Agent 项目")
    context_text = "\n".join(str(item) for item in context)

    assert "中文" in context_text
    assert "用户偏好中文解释技术方案" in context_text
