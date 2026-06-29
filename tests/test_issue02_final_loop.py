from app.contracts import MessageRole, SessionStatus
from app.llm.fake import ScriptedLLM
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.action_parser import ActionParser
from app.runtime.session_manager import SessionManager
from app.storage.sqlite_store import SQLiteStore


def test_single_session_final_answer_is_saved_to_messages():
    store = SQLiteStore(":memory:")
    store.init_schema()
    session_manager = SessionManager(store)
    runtime = AgentRuntime(
        session_manager=session_manager,
        llm_client=ScriptedLLM([
            {
                "type": "final",
                "thought_summary": "answer directly",
                "answer": "你好，我可以帮你记录待办。",
            }
        ]),
        action_parser=ActionParser(),
    )

    result = runtime.handle_user_message(
        user_id="user_A",
        session_id="window_1",
        content="你好",
    )

    assert result.answer == "你好，我可以帮你记录待办。"
    state = session_manager.get_state("user_A", "window_1")
    assert state.status == SessionStatus.COMPLETED
    assert [message.role for message in state.messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ]
    assert state.messages[0].content == "你好"
    assert state.messages[1].content == "你好，我可以帮你记录待办。"
