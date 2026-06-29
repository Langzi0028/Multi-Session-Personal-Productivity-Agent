from app.contracts import ErrorCode, SessionStatus, TraceStatus
from app.llm.fake import ScriptedLLM
from app.runtime.action_parser import ActionParser
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.session_manager import SessionManager
from app.runtime.trace_logger import TraceLogger
from app.storage.sqlite_store import SQLiteStore
from app.tools.calculator import CalculatorTool
from app.tools.registry import ToolRegistry


def build_runtime(responses, max_steps=5):
    store = SQLiteStore(":memory:")
    store.init_schema()
    session_manager = SessionManager(store)
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    trace_logger = TraceLogger(store)
    runtime = AgentRuntime(
        session_manager=session_manager,
        llm_client=ScriptedLLM(responses),
        action_parser=ActionParser(),
        tool_registry=registry,
        trace_logger=trace_logger,
        max_steps=max_steps,
    )
    return runtime, session_manager, trace_logger


def test_successful_tool_chain_writes_llm_and_tool_traces():
    runtime, _session_manager, trace_logger = build_runtime([
        {
            "type": "tool_call",
            "thought_summary": "need calculate",
            "tool_name": "calculator",
            "arguments": {"expression": "2 + 3 * 4"},
        },
        {
            "type": "final",
            "thought_summary": "done",
            "answer": "14",
        },
    ])

    result = runtime.handle_user_message("user_A", "window_1", "2 + 3 * 4 等于多少？")

    assert result.answer == "14"
    traces = trace_logger.list_traces("user_A", "window_1")
    assert [trace.action_type for trace in traces] == ["tool_call", "tool_result", "final"]
    assert traces[0].tool_name == "calculator"
    assert traces[0].arguments == {"expression": "2 + 3 * 4"}
    assert traces[1].result_summary.endswith("14")
    assert all(trace.status == TraceStatus.SUCCESS for trace in traces)


def test_tool_failure_writes_error_trace_and_returns_fallback():
    runtime, session_manager, trace_logger = build_runtime([
        {
            "type": "tool_call",
            "thought_summary": "bad calculate",
            "tool_name": "calculator",
            "arguments": {"expression": "__import__('os').system('bad')"},
        }
    ])

    result = runtime.handle_user_message("user_A", "window_1", "bad expression")

    assert result.session_status == SessionStatus.ERROR
    assert "工具调用失败" in result.answer
    state = session_manager.get_state("user_A", "window_1")
    assert state.status == SessionStatus.ERROR
    traces = trace_logger.list_traces("user_A", "window_1")
    assert traces[-1].status == TraceStatus.ERROR
    assert traces[-1].error == ErrorCode.TOOL_EXECUTION_ERROR.value


def test_repeated_identical_tool_call_uses_existing_result_instead_of_looping():
    runtime, _session_manager, trace_logger = build_runtime([
        {
            "type": "tool_call",
            "thought_summary": "need calculate",
            "tool_name": "calculator",
            "arguments": {"expression": "1 + 1"},
        },
        {
            "type": "tool_call",
            "thought_summary": "same calculate again",
            "tool_name": "calculator",
            "arguments": {"expression": "1 + 1"},
        },
    ])

    result = runtime.handle_user_message("user_A", "window_1", "1 + 1 等于多少？")

    assert result.session_status == SessionStatus.COMPLETED
    assert result.answer == "1 + 1 = 2"
    traces = trace_logger.list_traces("user_A", "window_1")
    assert [(trace.action_type, trace.tool_name) for trace in traces] == [
        ("tool_call", "calculator"),
        ("tool_result", "calculator"),
        ("final", None),
    ]
    assert all(trace.status == TraceStatus.SUCCESS for trace in traces)



def test_max_steps_stops_loop_and_writes_trace():
    runtime, _session_manager, trace_logger = build_runtime([
        {
            "type": "tool_call",
            "thought_summary": "again",
            "tool_name": "calculator",
            "arguments": {"expression": "1 + 1"},
        },
        {
            "type": "tool_call",
            "thought_summary": "again",
            "tool_name": "calculator",
            "arguments": {"expression": "2 + 2"},
        },
        {
            "type": "tool_call",
            "thought_summary": "again",
            "tool_name": "calculator",
            "arguments": {"expression": "3 + 3"},
        },
    ], max_steps=2)

    result = runtime.handle_user_message("user_A", "window_1", "loop")

    assert result.session_status == SessionStatus.ERROR
    assert "停止继续执行" in result.answer
    traces = trace_logger.list_traces("user_A", "window_1")
    assert traces[-1].status == TraceStatus.ERROR
    assert traces[-1].error == ErrorCode.MAX_STEPS_EXCEEDED.value
