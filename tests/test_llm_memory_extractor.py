from app.memory.extractor import HeuristicMemoryExtractor, LLMMemoryExtractor


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


def test_llm_memory_extractor_parses_structured_memory_json():
    client = FakeJsonClient(
        {
            "profile_updates": {
                "preferred_language": "中文",
                "answer_style": "简洁直接",
                "common_topics": ["Agent Runtime"],
                "timezone": "Asia/Shanghai",
            },
            "semantic_memories": ["用户正在准备 Agent 开发岗笔试。"],
            "episodic_memories": [
                {
                    "event_type": "turn_completed",
                    "content": "用户要求实现 LLM 版记忆抽取器。",
                    "summary": "讨论 LLM memory extractor。",
                    "importance": 0.7,
                }
            ],
        }
    )
    extractor = LLMMemoryExtractor(client, fallback=HeuristicMemoryExtractor(), model="memory-model", timeout_seconds=7)

    extraction = extractor.extract("请记住：我偏好中文简洁回答。", "好的。", ["工具结果"])

    assert extraction.profile_updates == {
        "preferred_language": "中文",
        "answer_style": "简洁直接",
        "common_topics": ["Agent Runtime"],
        "timezone": "Asia/Shanghai",
    }
    assert extraction.semantic_memories == ["用户正在准备 Agent 开发岗笔试。"]
    assert extraction.episodic_memories == [
        {
            "event_type": "turn_completed",
            "content": "用户要求实现 LLM 版记忆抽取器。",
            "summary": "讨论 LLM memory extractor。",
            "importance": 0.7,
        }
    ]
    assert client.calls[0]["model"] == "memory-model"
    assert client.calls[0]["timeout"] == 7
    assert client.calls[0]["payload"]["tool_summaries"] == ["工具结果"]


def test_llm_memory_extractor_falls_back_when_client_fails():
    client = FakeJsonClient(error=RuntimeError("upstream failed"))
    extractor = LLMMemoryExtractor(client, fallback=HeuristicMemoryExtractor())

    extraction = extractor.extract(
        "请记住：我偏好中文简洁回答，我正在准备 Agent 开发岗笔试。",
        "好的。",
        [],
    )

    assert extraction.profile_updates["preferred_language"] == "中文"
    assert extraction.profile_updates["answer_style"] == "简洁直接"
    assert any("Agent 开发岗笔试" in item for item in extraction.semantic_memories)
    assert extraction.episodic_memories[0]["event_type"] == "turn_completed"


def test_llm_memory_extractor_sanitizes_invalid_and_sensitive_output():
    client = FakeJsonClient(
        {
            "profile_updates": {
                "preferred_language": "中文",
                "unknown": "ignored",
                "common_topics": "Agent Runtime",
            },
            "semantic_memories": [
                "用户偏好代码干净整洁高效。",
                "API key 是 sk-secret-value",
                "",
            ],
            "episodic_memories": [
                {
                    "event_type": "turn_completed",
                    "content": "用户要求使用 LLM 抽取记忆。",
                    "summary": "LLM 抽取记忆",
                    "importance": 2.5,
                },
                {"event_type": "turn_completed", "content": "password=123456", "importance": 0.5},
            ],
        }
    )
    extractor = LLMMemoryExtractor(client, fallback=HeuristicMemoryExtractor())

    extraction = extractor.extract("做 LLM 版本", "好的。", [])

    assert extraction.profile_updates == {"preferred_language": "中文"}
    assert extraction.semantic_memories == ["用户偏好代码干净整洁高效。"]
    assert extraction.episodic_memories == [
        {
            "event_type": "turn_completed",
            "content": "用户要求使用 LLM 抽取记忆。",
            "summary": "LLM 抽取记忆",
            "importance": 1.0,
        }
    ]


def test_llm_memory_extractor_falls_back_on_invalid_response_shape():
    client = FakeJsonClient({"profile_updates": [], "semantic_memories": "bad", "episodic_memories": {}})
    extractor = LLMMemoryExtractor(client, fallback=HeuristicMemoryExtractor())

    extraction = extractor.extract("请记住：我偏好中文简洁回答。", "好的。", [])

    assert extraction.profile_updates["preferred_language"] == "中文"
    assert extraction.episodic_memories[0]["event_type"] == "turn_completed"
