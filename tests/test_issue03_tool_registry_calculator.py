import pytest

from app.contracts import MessageRole
from app.llm.fake import ScriptedLLM
from app.runtime.action_parser import ActionParser, ActionParserError
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.session_manager import SessionManager
from app.storage.sqlite_store import SQLiteStore
from app.tools.calculator import CalculatorTool
from app.tools.registry import ToolRegistry, ToolRegistryError


def test_tool_registry_registers_and_exports_schema():
    registry = ToolRegistry()
    registry.register(CalculatorTool())

    schema = registry.schemas()
    assert schema[0]["name"] == "calculator"
    assert schema[0]["parameters"]["required"] == ["expression"]

    with pytest.raises(ToolRegistryError):
        registry.register(CalculatorTool())

    with pytest.raises(ToolRegistryError):
        registry.get("missing")


def test_calculator_validates_required_expression():
    registry = ToolRegistry()
    registry.register(CalculatorTool())

    with pytest.raises(ToolRegistryError):
        registry.execute("calculator", {})


def test_action_parser_rejects_unknown_action_type():
    with pytest.raises(ActionParserError):
        ActionParser().parse({"type": "unknown"})


def test_agent_runtime_calls_calculator_then_final_answer():
    store = SQLiteStore(":memory:")
    store.init_schema()
    session_manager = SessionManager(store)
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    runtime = AgentRuntime(
        session_manager=session_manager,
        llm_client=ScriptedLLM([
            {
                "type": "tool_call",
                "thought_summary": "need calculate",
                "tool_name": "calculator",
                "arguments": {"expression": "2 + 3 * 4"},
            },
            {
                "type": "final",
                "thought_summary": "calculator returned 14",
                "answer": "2 + 3 * 4 = 14",
            },
        ]),
        action_parser=ActionParser(),
        tool_registry=registry,
    )

    result = runtime.handle_user_message(
        user_id="user_A",
        session_id="window_1",
        content="2 + 3 * 4 等于多少？",
    )

    assert result.answer == "2 + 3 * 4 = 14"
    state = session_manager.get_state("user_A", "window_1")
    assert [message.role for message in state.messages] == [
        MessageRole.USER,
        MessageRole.TOOL,
        MessageRole.ASSISTANT,
    ]
    assert "14" in state.messages[1].content
