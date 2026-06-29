from app.contracts import AsyncJobStatus, SessionStatus
from app.runtime.async_manager import AsyncManager
from app.runtime.session_manager import SessionManager
from app.runtime.trace_logger import TraceLogger
from app.storage.sqlite_store import SQLiteStore
from app.tools.long_search import LongSearchTool


def test_long_search_submits_job_and_completion_writes_current_session_event_and_trace():
    store = SQLiteStore(":memory:")
    store.init_schema()
    session_manager = SessionManager(store)
    trace_logger = TraceLogger(store)
    async_manager = AsyncManager(store, session_manager, trace_logger)
    tool = LongSearchTool(async_manager)

    submitted = tool.run(
        {"query": "Agent Runtime"},
        context={"user_id": "user_A", "session_id": "window_1"},
    )

    assert submitted["status"] == AsyncJobStatus.SUBMITTED.value
    assert submitted["job_id"].startswith("job_")
    assert session_manager.get_state("user_A", "window_1").status == SessionStatus.WAITING_ASYNC_TOOL

    async_manager.complete_job(submitted["job_id"], {"summary": "Agent Runtime 长搜索完成"})

    job = async_manager.get_job(submitted["job_id"])
    assert job["status"] == AsyncJobStatus.COMPLETED.value
    state = session_manager.get_state("user_A", "window_1")
    assert state.recent_tool_results == [{"job_id": submitted["job_id"], "summary": "Agent Runtime 长搜索完成"}]
    traces = trace_logger.list_traces("user_A", "window_1")
    assert traces[-1].action_type == "async_tool_completed"
    assert traces[-1].result_summary == "Agent Runtime 长搜索完成"


def test_cancel_event_priority_and_single_writer_guard():
    store = SQLiteStore(":memory:")
    store.init_schema()
    session_manager = SessionManager(store)
    trace_logger = TraceLogger(store)
    async_manager = AsyncManager(store, session_manager, trace_logger)

    async_manager.mark_running("user_A", "window_1")
    assert async_manager.try_acquire_writer("user_A", "window_1") is False
    async_manager.enqueue_event("user_A", "window_1", {"type": "UserMessageEvent", "content": "later"})
    async_manager.enqueue_event("user_A", "window_1", {"type": "CancelEvent"})

    events = async_manager.drain_events("user_A", "window_1")
    assert [event["type"] for event in events] == ["CancelEvent", "UserMessageEvent"]
