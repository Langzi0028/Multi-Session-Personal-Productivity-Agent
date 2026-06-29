from __future__ import annotations

from app.contracts import MessageRole
from app.memory.manager import MemoryManager
from app.runtime.context_summarizer import ContextSummarizer, RuleBasedContextSummarizer
from app.runtime.session_manager import SessionManager


class ContextManager:
    def __init__(
        self,
        session_manager: SessionManager,
        recent_message_limit: int = 10,
        memory_manager: MemoryManager | None = None,
        context_summarizer: ContextSummarizer | None = None,
    ) -> None:
        self.session_manager = session_manager
        self.recent_message_limit = recent_message_limit
        self.memory_manager = memory_manager
        self.context_summarizer = context_summarizer or RuleBasedContextSummarizer()

    def compress_if_needed(self, user_id: str, session_id: str, max_message_count: int = 30) -> bool:
        state = self.session_manager.get_state(user_id, session_id)
        keep_count = max(1, self.recent_message_limit)
        compression_threshold = min(max_message_count, keep_count)
        if len(state.messages) <= compression_threshold:
            return False

        old_messages = state.messages[:-keep_count]
        if not old_messages:
            return False

        summary = self.context_summarizer.summarize(state.session_summary.strip(), old_messages)
        self.session_manager.update_summary(user_id, session_id, summary)
        return True

    def build_context(self, user_id: str, session_id: str, current_input: str) -> list[dict[str, object]]:
        state = self.session_manager.get_state(user_id, session_id)
        recent_messages = state.messages[-self.recent_message_limit :]
        recent_tool_results = [
            {"role": message.role.value, "content": message.content}
            for message in recent_messages
            if message.role == MessageRole.TOOL
        ]
        todos = [todo.model_dump() for todo in state.todos]
        profile = self.memory_manager.get_profile(user_id) if self.memory_manager else None
        memories = self.memory_manager.retrieve(user_id, current_input) if self.memory_manager else []

        return [
            {"section": "system_prompt", "content": "你是一个多 Session 个人效率 Agent。"},
            {"section": "user_profile", "content": profile},
            {"section": "relevant_long_term_memory", "items": memories},
            {"section": "session_summary", "content": state.session_summary},
            {"section": "todos", "items": todos},
            {"section": "recent_tool_results", "items": recent_tool_results},
            {
                "section": "recent_messages",
                "items": [
                    {"role": message.role.value, "content": message.content}
                    for message in recent_messages
                ],
            },
            {"section": "current_user_input", "content": current_input},
        ]
