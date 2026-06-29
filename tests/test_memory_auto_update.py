from app.contracts import MessageRole
from app.llm.fake import ScriptedLLM
from app.memory.extractor import MemoryExtraction
from app.memory.manager import MemoryManager
from app.memory.vector_store import VectorMemoryHit
from app.runtime.action_parser import ActionParser
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.session_manager import SessionManager
from app.runtime.trace_logger import TraceLogger
from app.storage.sqlite_store import SQLiteStore
from app.tools.calculator import CalculatorTool
from app.tools.registry import ToolRegistry


class RecordingVectorStore:
    def __init__(self):
        self.upserts = []
        self.hits = []
        self.raise_on_query = False
        self.raise_on_upsert = False

    def upsert(self, memory_id, content, metadata):
        if self.raise_on_upsert:
            raise RuntimeError("vector unavailable")
        self.upserts.append({"memory_id": memory_id, "content": content, "metadata": metadata})

    def query(self, user_id, query, limit):
        if self.raise_on_query:
            raise RuntimeError("vector unavailable")
        return self.hits[:limit]


class NoisyExtractor:
    def extract(self, user_input, assistant_answer, tool_summaries=None):
        return MemoryExtraction(
            profile_updates={
                "preferred_language": "中文",
                "unknown": "ignored",
                "common_topics": "bad-shape",
            },
            semantic_memories=["用户偏好代码干净整洁高效。", "", "token=abc"],
            episodic_memories=[
                {
                    "event_type": "turn_completed",
                    "content": "用户要求实现 LLM 版记忆抽取器。",
                    "summary": "LLM 记忆抽取",
                    "importance": 2.5,
                },
                {"event_type": "turn_completed", "content": "password=123456", "importance": 0.5},
            ],
        )


class SemanticOnlyExtractor:
    def extract(self, user_input, assistant_answer, tool_summaries=None):
        return MemoryExtraction(
            profile_updates={"preferred_language": "中文"},
            semantic_memories=["用户正在准备 Agent 开发岗笔试。"],
            episodic_memories=[],
        )


def test_memory_manager_updates_profile_semantic_and_episodic_memory_after_turn():
    store = SQLiteStore(":memory:")
    store.init_schema()
    vector_store = RecordingVectorStore()
    memory = MemoryManager(store, vector_store=vector_store)

    memory.update_from_turn(
        user_id="user_A",
        session_id="window_1",
        user_input="请记住：我偏好中文简洁回答，我正在准备 Agent 开发岗笔试。",
        assistant_answer="好的，我会记住你的偏好和目标。",
        tool_summaries=[],
    )

    profile = memory.get_profile("user_A")
    assert profile["preferred_language"] == "中文"
    assert profile["answer_style"] == "简洁直接"

    semantic_rows = store.query_all("SELECT * FROM semantic_memories WHERE user_id = ?", ("user_A",))
    assert any("Agent 开发岗笔试" in row["content"] for row in semantic_rows)
    assert all(row["embedding_id"] for row in semantic_rows)

    episodic_rows = store.query_all("SELECT * FROM episodic_memories WHERE user_id = ?", ("user_A",))
    assert len(episodic_rows) == 1
    assert episodic_rows[0]["event_type"] == "turn_completed"
    assert "请记住" in episodic_rows[0]["content"]
    assert episodic_rows[0]["embedding_id"]
    assert {item["metadata"]["memory_type"] for item in vector_store.upserts} == {"semantic", "episodic"}


def test_memory_manager_sanitizes_extractor_output_before_storage():
    store = SQLiteStore(":memory:")
    store.init_schema()
    memory = MemoryManager(store, vector_store=RecordingVectorStore(), extractor=NoisyExtractor())

    memory.update_from_turn("user_A", "window_1", "做 LLM 版本", "好的。", [])

    profile = memory.get_profile("user_A")
    assert profile["preferred_language"] == "中文"
    assert profile["common_topics"] == []
    semantic_rows = store.query_all("SELECT content FROM semantic_memories WHERE user_id = ?", ("user_A",))
    assert [row["content"] for row in semantic_rows] == ["用户偏好代码干净整洁高效。"]
    episodic_rows = store.query_all("SELECT * FROM episodic_memories WHERE user_id = ?", ("user_A",))
    assert len(episodic_rows) == 1
    assert episodic_rows[0]["content"] == "用户要求实现 LLM 版记忆抽取器。"
    assert episodic_rows[0]["importance"] == 1.0



def test_memory_manager_adds_fallback_episodic_memory_when_extractor_omits_it():
    store = SQLiteStore(":memory:")
    store.init_schema()
    memory = MemoryManager(store, vector_store=RecordingVectorStore(), extractor=SemanticOnlyExtractor())

    memory.update_from_turn(
        user_id="user_A",
        session_id="window_1",
        user_input="请记住：我偏好中文简洁回答，我正在准备 Agent 开发岗笔试。",
        assistant_answer="已记住。",
        tool_summaries=[],
    )

    episodic_rows = store.query_all("SELECT * FROM episodic_memories WHERE user_id = ?", ("user_A",))
    assert len(episodic_rows) == 1
    assert episodic_rows[0]["event_type"] == "turn_completed"
    assert "Agent 开发岗笔试" in episodic_rows[0]["content"]



def test_agent_runtime_updates_memory_once_after_successful_tool_turn_without_extra_traces():
    store = SQLiteStore(":memory:")
    store.init_schema()
    session_manager = SessionManager(store)
    trace_logger = TraceLogger(store)
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    memory = MemoryManager(store, vector_store=RecordingVectorStore())
    runtime = AgentRuntime(
        session_manager=session_manager,
        llm_client=ScriptedLLM([
            {
                "type": "tool_call",
                "thought_summary": "need calculate",
                "tool_name": "calculator",
                "arguments": {"expression": "2 + 3"},
            },
            {
                "type": "final",
                "thought_summary": "done",
                "answer": "2 + 3 = 5",
            },
        ]),
        action_parser=ActionParser(),
        tool_registry=registry,
        trace_logger=trace_logger,
        memory_manager=memory,
    )

    result = runtime.handle_user_message("user_A", "window_1", "请记住这次计算：2 + 3")

    assert result.answer == "2 + 3 = 5"
    traces = trace_logger.list_traces("user_A", "window_1")
    assert [trace.action_type for trace in traces] == ["tool_call", "tool_result", "final"]
    episodic_rows = store.query_all("SELECT * FROM episodic_memories WHERE user_id = ?", ("user_A",))
    assert len(episodic_rows) == 1
    assert "2 + 3 = 5" in episodic_rows[0]["content"]
    assert [message.role for message in session_manager.get_state("user_A", "window_1").messages] == [
        MessageRole.USER,
        MessageRole.TOOL,
        MessageRole.ASSISTANT,
    ]


def test_vector_recall_fetches_sqlite_rows_and_keeps_user_isolation():
    store = SQLiteStore(":memory:")
    store.init_schema()
    vector_store = RecordingVectorStore()
    memory = MemoryManager(store, vector_store=vector_store)
    user_a_id = memory.add_semantic_memory("user_A", "用户偏好中文解释技术方案。", source_session_id="window_1")
    user_b_id = memory.add_episodic_memory("user_B", "window_9", "turn_completed", "user_B 的私有记忆。")
    vector_store.hits = [
        VectorMemoryHit("semantic", f"semantic:{user_a_id}", user_a_id, 0.1, "用户偏好中文解释技术方案。", {}),
        VectorMemoryHit("episodic", f"episodic:{user_b_id}", user_b_id, 0.2, "user_B 的私有记忆。", {}),
    ]

    recalled = memory.retrieve("user_A", "我偏好什么解释方式？")

    assert recalled == [{"type": "semantic", "content": "用户偏好中文解释技术方案。"}]


def test_vector_store_failure_falls_back_to_sqlite_recall():
    store = SQLiteStore(":memory:")
    store.init_schema()
    vector_store = RecordingVectorStore()
    vector_store.raise_on_query = True
    memory = MemoryManager(store, vector_store=vector_store)
    memory.add_semantic_memory("user_A", "用户正在准备 Agent 开发岗笔试。", source_session_id="window_1")

    recalled = memory.retrieve("user_A", "之前我让你记住什么？")

    assert recalled == [{"type": "semantic", "content": "用户正在准备 Agent 开发岗笔试。"}]
