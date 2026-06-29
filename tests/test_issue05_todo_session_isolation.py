from app.contracts import TodoStatus
from app.llm.fake import ScriptedLLM
from app.runtime.action_parser import ActionParser
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.session_manager import SessionManager
from app.runtime.trace_logger import TraceLogger
from app.storage.sqlite_store import SQLiteStore
from app.tools.registry import ToolRegistry
from app.tools.todo import TodoTool


def build_runtime(responses):
    store = SQLiteStore(":memory:")
    store.init_schema()
    session_manager = SessionManager(store)
    registry = ToolRegistry()
    registry.register(TodoTool(session_manager))
    trace_logger = TraceLogger(store)
    runtime = AgentRuntime(
        session_manager=session_manager,
        llm_client=ScriptedLLM(responses),
        action_parser=ActionParser(),
        tool_registry=registry,
        trace_logger=trace_logger,
    )
    return runtime, session_manager, trace_logger


def test_todo_tool_isolated_by_user_and_session():
    runtime, session_manager, trace_logger = build_runtime([
        {
            "type": "tool_call",
            "thought_summary": "add todo",
            "tool_name": "todo",
            "arguments": {"action": "add", "content": "晚上 8 点带伞出门"},
        },
        {"type": "final", "thought_summary": "done", "answer": "已记录带伞待办。"},
        {
            "type": "tool_call",
            "thought_summary": "add todo",
            "tool_name": "todo",
            "arguments": {"action": "add", "content": "明天上午整理 README"},
        },
        {"type": "final", "thought_summary": "done", "answer": "已记录 README 待办。"},
    ])

    runtime.handle_user_message("user_A", "window_1", "帮我记一个待办：晚上 8 点带伞出门")
    runtime.handle_user_message("user_A", "window_2", "帮我记一个待办：明天上午整理 README")

    window_1 = session_manager.list_todos("user_A", "window_1")
    window_2 = session_manager.list_todos("user_A", "window_2")

    assert [todo.content for todo in window_1] == ["晚上 8 点带伞出门"]
    assert [todo.content for todo in window_2] == ["明天上午整理 README"]
    assert session_manager.get_state("user_A", "window_1").messages[0].content != session_manager.get_state("user_A", "window_2").messages[0].content
    assert len(trace_logger.list_traces("user_A", "window_1")) == 3
    assert len(trace_logger.list_traces("user_A", "window_2")) == 3


def test_todo_done_updates_only_current_session():
    runtime, session_manager, _trace_logger = build_runtime([
        {
            "type": "tool_call",
            "thought_summary": "add todo",
            "tool_name": "todo",
            "arguments": {"action": "add", "content": "晚上 8 点带伞出门"},
        },
        {"type": "final", "thought_summary": "done", "answer": "added"},
        {
            "type": "tool_call",
            "thought_summary": "done todo",
            "tool_name": "todo",
            "arguments": {"action": "done", "content": "晚上 8 点带伞出门"},
        },
        {"type": "final", "thought_summary": "done", "answer": "done"},
    ])

    runtime.handle_user_message("user_A", "window_1", "添加待办")
    runtime.handle_user_message("user_A", "window_1", "完成带伞待办")

    todos = session_manager.list_todos("user_A", "window_1")
    assert todos[0].status == TodoStatus.DONE
    assert session_manager.list_todos("user_A", "window_2") == []
