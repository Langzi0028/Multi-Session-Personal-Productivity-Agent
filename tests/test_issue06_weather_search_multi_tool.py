from app.llm.fake import ScriptedLLM
from app.runtime.action_parser import ActionParser
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.session_manager import SessionManager
from app.runtime.trace_logger import TraceLogger
from app.storage.sqlite_store import SQLiteStore
from app.tools.registry import ToolRegistry
from app.tools.search import SearchTool
from app.tools.todo import TodoTool
from app.tools.weather import WeatherTool


def test_weather_and_todo_can_run_in_one_user_message_with_ordered_trace():
    store = SQLiteStore(":memory:")
    store.init_schema()
    session_manager = SessionManager(store)
    registry = ToolRegistry()
    registry.register(WeatherTool())
    registry.register(SearchTool())
    registry.register(TodoTool(session_manager))
    trace_logger = TraceLogger(store)
    runtime = AgentRuntime(
        session_manager=session_manager,
        llm_client=ScriptedLLM([
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
        ]),
        action_parser=ActionParser(),
        tool_registry=registry,
        trace_logger=trace_logger,
    )

    result = runtime.handle_user_message(
        "user_A",
        "window_1",
        "北京今天天气怎么样？顺便帮我记一个待办：晚上 8 点带伞出门。",
    )

    assert "北京今天多云" in result.answer
    assert "晚上 8 点带伞出门" in result.answer
    assert [todo.content for todo in session_manager.list_todos("user_A", "window_1")] == ["晚上 8 点带伞出门"]
    traces = trace_logger.list_traces("user_A", "window_1")
    assert [(trace.action_type, trace.tool_name) for trace in traces] == [
        ("tool_call", "weather"),
        ("tool_result", "weather"),
        ("tool_call", "todo"),
        ("tool_result", "todo"),
        ("final", None),
    ]


def test_search_mock_returns_query_summary():
    tool = SearchTool()
    result = tool.run({"query": "Agent Runtime"})
    assert "Agent Runtime" in result["summary"]
