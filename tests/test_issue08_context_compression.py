from app.contracts import Message, MessageRole
from app.runtime.context_manager import ContextManager
from app.runtime.context_summarizer import LLMContextSummarizer, RuleBasedContextSummarizer
from app.runtime.session_manager import SessionManager
from app.storage.sqlite_store import SQLiteStore


class RecordingSummarizer:
    def __init__(self, summary: str = "LLM 压缩摘要") -> None:
        self.summary = summary
        self.calls = []

    def summarize(self, existing_summary, old_messages):
        self.calls.append({"existing_summary": existing_summary, "old_messages": list(old_messages)})
        contents = " / ".join(message.content for message in old_messages)
        return f"{self.summary}: {contents}"


class FakeJsonClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def complete_json(self, system_prompt, payload, model=None, timeout=30):
        self.calls.append({"system_prompt": system_prompt, "payload": payload, "model": model, "timeout": timeout})
        if self.error:
            raise self.error
        return self.response


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


def test_compress_triggers_when_messages_exceed_recent_window_before_legacy_threshold():
    store = SQLiteStore(":memory:")
    store.init_schema()
    session_manager = SessionManager(store)
    summarizer = RecordingSummarizer("窗口外消息摘要")
    context_manager = ContextManager(
        session_manager,
        recent_message_limit=10,
        context_summarizer=summarizer,
    )

    for index in range(15):
        session_manager.add_message("user_A", "window_1", MessageRole.USER, f"message-{index}")

    compressed = context_manager.compress_if_needed("user_A", "window_1", max_message_count=30)

    assert compressed is True
    assert len(summarizer.calls) == 1
    assert [message.content for message in summarizer.calls[0]["old_messages"]] == [
        "message-0",
        "message-1",
        "message-2",
        "message-3",
        "message-4",
    ]

    context = context_manager.build_context("user_A", "window_1", "继续")
    summary_section = next(item for item in context if item["section"] == "session_summary")
    recent_section = next(item for item in context if item["section"] == "recent_messages")

    assert "message-0" in str(summary_section)
    assert "message-4" in str(summary_section)
    assert "message-0" not in str(recent_section)
    assert "message-5" in str(recent_section)
    assert "message-14" in str(recent_section)


def test_compress_not_triggered_when_under_recent_window():
    store = SQLiteStore(":memory:")
    store.init_schema()
    session_manager = SessionManager(store)
    summarizer = RecordingSummarizer()
    context_manager = ContextManager(session_manager, recent_message_limit=10, context_summarizer=summarizer)
    session_manager.add_message("user_A", "window_1", MessageRole.USER, "hello")

    compressed = context_manager.compress_if_needed("user_A", "window_1", max_message_count=6)

    assert compressed is False
    assert summarizer.calls == []
    assert session_manager.get_state("user_A", "window_1").session_summary == ""


def test_llm_context_summarizer_uses_json_client_response():
    client = FakeJsonClient({"summary": "用户前面确认了项目重点和录屏顺序。"})
    summarizer = LLMContextSummarizer(client, model="summary-model", timeout_seconds=7)

    summary = summarizer.summarize(
        "已有摘要",
        [Message(role=MessageRole.USER, content="请记住项目重点是 Runtime。")],
    )

    assert summary == "用户前面确认了项目重点和录屏顺序。"
    assert client.calls[0]["model"] == "summary-model"
    assert client.calls[0]["timeout"] == 7
    assert client.calls[0]["payload"]["existing_summary"] == "已有摘要"
    assert client.calls[0]["payload"]["messages"] == [
        {"role": "user", "content": "请记住项目重点是 Runtime。"}
    ]


def test_llm_context_summarizer_falls_back_when_client_fails():
    client = FakeJsonClient(error=RuntimeError("upstream failed"))
    summarizer = LLMContextSummarizer(client, fallback=RuleBasedContextSummarizer())

    summary = summarizer.summarize(
        "已有摘要",
        [Message(role=MessageRole.USER, content="早期关键信息：周五下午带伞。")],
    )

    assert "已有摘要" in summary
    assert "早期关键信息：周五下午带伞。" in summary
