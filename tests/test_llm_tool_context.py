from __future__ import annotations

from app.llm.fake import ScriptedLLM
from app.llm.openai_client import OpenAICompatibleClient
from app.runtime.action_parser import ActionParser
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.session_manager import SessionManager
from app.storage.sqlite_store import SQLiteStore
from app.tools.registry import ToolRegistry


class CustomLookupTool:
    name = "custom_lookup"
    description = "查询自定义资料。"
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "查询关键词",
            }
        },
        "required": ["query"],
    }
    timeout = 3.0
    is_async = False
    permission = "none"

    def run(self, arguments: dict[str, object], context: dict[str, object] | None = None) -> dict[str, object]:
        return {"summary": f"lookup:{arguments['query']}"}


def test_registered_tools_are_exposed_to_llm_context_without_hardcoding():
    store = SQLiteStore(":memory:")
    store.init_schema()
    session_manager = SessionManager(store)
    registry = ToolRegistry()
    registry.register(CustomLookupTool())
    llm = ScriptedLLM([
        {
            "type": "final",
            "thought_summary": "done",
            "answer": "ok",
        }
    ])
    runtime = AgentRuntime(
        session_manager=session_manager,
        llm_client=llm,
        action_parser=ActionParser(),
        tool_registry=registry,
    )

    runtime.handle_user_message("user_A", "window_1", "查一下项目资料")

    available_tools = next(section for section in llm.calls[0] if section["section"] == "available_tools")
    assert available_tools["items"] == registry.schemas()
    assert available_tools["items"][0]["name"] == "custom_lookup"


def test_tool_call_and_tool_result_are_added_to_current_turn_events():
    store = SQLiteStore(":memory:")
    store.init_schema()
    session_manager = SessionManager(store)
    registry = ToolRegistry()
    registry.register(CustomLookupTool())
    llm = ScriptedLLM([
        {
            "type": "tool_call",
            "thought_summary": "need lookup",
            "tool_name": "custom_lookup",
            "arguments": {"query": "项目资料"},
        },
        {
            "type": "final",
            "thought_summary": "done",
            "answer": "查询完成。",
        },
    ])
    runtime = AgentRuntime(
        session_manager=session_manager,
        llm_client=llm,
        action_parser=ActionParser(),
        tool_registry=registry,
    )

    runtime.handle_user_message("user_A", "window_1", "查一下项目资料")

    first_turn_events = next(section for section in llm.calls[0] if section["section"] == "current_turn_events")
    assert first_turn_events["items"] == [{"role": "user", "content": "查一下项目资料"}]

    second_turn_events = next(section for section in llm.calls[1] if section["section"] == "current_turn_events")
    assert second_turn_events["items"] == [
        {"role": "user", "content": "查一下项目资料"},
        {
            "role": "assistant_action",
            "type": "tool_call",
            "tool_name": "custom_lookup",
            "arguments": {"query": "项目资料"},
        },
        {
            "role": "tool_result",
            "tool_name": "custom_lookup",
            "content": "lookup:项目资料",
        },
    ]



def test_openai_client_system_prompt_tells_model_to_use_available_tools():
    client = OpenAICompatibleClient.__new__(OpenAICompatibleClient)
    client.model = "test-model"
    captured: dict[str, object] = {}

    def fake_complete_json(
        system_prompt: str,
        payload: object,
        model: str | None = None,
        timeout: float = 60,
    ) -> dict[str, object]:
        captured["system_prompt"] = system_prompt
        captured["payload"] = payload
        return {"type": "final", "thought_summary": "done", "answer": "ok"}

    client.complete_json = fake_complete_json

    client.complete([
        {
            "section": "available_tools",
            "items": [
                {
                    "name": "custom_lookup",
                    "description": "查询自定义资料。",
                    "parameters": CustomLookupTool.parameters_schema,
                }
            ],
        }
    ])

    system_prompt = str(captured["system_prompt"])
    assert "available_tools" in system_prompt
    assert "current_turn_events" in system_prompt
    assert "current_user_input" in system_prompt
    assert "tool_call" in system_prompt
    assert "工具参数" in system_prompt
    assert "不能直接回答无法获取" in system_prompt
    assert "relevant_long_term_memory" in system_prompt
    assert "user_profile" in system_prompt
    assert "semantic_memory" in system_prompt
    assert "episodic_memory" in system_prompt
