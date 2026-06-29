from __future__ import annotations

import json

from pydantic import BaseModel

from app.contracts import ErrorCode, FinalAction, MessageRole, SessionStatus, ToolCallAction, TraceStatus
from app.llm.base import LLMClient
from app.memory.manager import MemoryManager
from app.runtime.action_parser import ActionParser, ActionParserError
from app.runtime.context_manager import ContextManager
from app.runtime.context_summarizer import ContextSummarizer
from app.runtime.session_manager import SessionManager
from app.runtime.trace_logger import TraceLogger
from app.tools.registry import ToolRegistry, ToolRegistryError


class AgentResult(BaseModel):
    answer: str
    session_status: SessionStatus


class AgentRuntime:
    def __init__(
        self,
        session_manager: SessionManager,
        llm_client: LLMClient,
        action_parser: ActionParser,
        tool_registry: ToolRegistry | None = None,
        trace_logger: TraceLogger | None = None,
        max_steps: int = 5,
        memory_manager: MemoryManager | None = None,
        context_summarizer: ContextSummarizer | None = None,
    ) -> None:
        self.session_manager = session_manager
        self.llm_client = llm_client
        self.action_parser = action_parser
        self.tool_registry = tool_registry
        self.trace_logger = trace_logger
        self.max_steps = max_steps
        self.memory_manager = memory_manager
        self.context_manager = ContextManager(
            session_manager,
            memory_manager=memory_manager,
            context_summarizer=context_summarizer,
        )

    def handle_user_message(self, user_id: str, session_id: str, content: str) -> AgentResult:
        """Run the fixed hand-rolled workflow for one user message."""
        # 1. 准备 session，并把当前用户消息写入 SQLite 事实源。
        self.session_manager.ensure_session(user_id, session_id)
        self.session_manager.set_status(user_id, session_id, SessionStatus.RUNNING)
        self.session_manager.add_message(user_id, session_id, MessageRole.USER, content)
        self.context_manager.compress_if_needed(user_id, session_id)

        step = 1
        tool_summaries: list[str] = []
        executed_tools: dict[str, str] = {}
        turn_events: list[dict[str, object]] = [{"role": "user", "content": content}]
        while True:
            try:
                # 2. 每一轮都从 SQLite 聚合最新上下文和已注册工具，再让 LLM 返回项目自有 JSON action。
                context = self._build_llm_context(user_id, session_id, content, turn_events)
                action = self.action_parser.parse(self.llm_client.complete(context))
            except ActionParserError as exc:
                return self._fallback_with_error(user_id, session_id, step, exc.error_code)
            except Exception:
                return self._fallback_with_error(user_id, session_id, step, ErrorCode.LLM_API_ERROR)

            # 3. final action 结束 workflow：保存 assistant 消息、写 final trace、返回结果。
            if isinstance(action, FinalAction):
                return self._finalize(user_id, session_id, step, action, content, tool_summaries)

            # 4. tool_call action 执行工具并把 tool result 写回消息，随后进入下一轮。
            if isinstance(action, ToolCallAction):
                tool_key = self._tool_call_key(action)
                if tool_key in executed_tools:
                    return self._finalize_from_repeated_tool_result(
                        user_id,
                        session_id,
                        step,
                        action,
                        content,
                        tool_summaries,
                        executed_tools[tool_key],
                    )
                if step > self.max_steps:
                    return self._fallback_with_error(user_id, session_id, step, ErrorCode.MAX_STEPS_EXCEEDED)
                try:
                    summary = self._execute_tool_action(user_id, session_id, step, action)
                    executed_tools[tool_key] = summary
                    tool_summaries.append(summary)
                    turn_events.extend(self._tool_turn_events(action, summary))
                except ToolRegistryError as exc:
                    return self._fallback_with_error(user_id, session_id, step, exc.error_code)
                step += 1
                continue

            return self._fallback_with_error(user_id, session_id, step, ErrorCode.INVALID_LLM_OUTPUT)

    def _build_llm_context(
        self,
        user_id: str,
        session_id: str,
        content: str,
        turn_events: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        context = self.context_manager.build_context(user_id, session_id, content)
        context.append({"section": "current_turn_events", "items": [dict(event) for event in turn_events]})
        if self.tool_registry is not None:
            context.append({"section": "available_tools", "items": self.tool_registry.schemas()})
        return context

    def _tool_turn_events(self, action: ToolCallAction, summary: str) -> list[dict[str, object]]:
        return [
            {
                "role": "assistant_action",
                "type": "tool_call",
                "tool_name": action.tool_name,
                "arguments": action.arguments,
            },
            {
                "role": "tool_result",
                "tool_name": action.tool_name,
                "content": summary,
            },
        ]

    def _tool_call_key(self, action: ToolCallAction) -> str:
        return json.dumps(
            {"tool_name": action.tool_name, "arguments": action.arguments},
            ensure_ascii=False,
            sort_keys=True,
        )

    def _finalize_from_repeated_tool_result(
        self,
        user_id: str,
        session_id: str,
        step: int,
        action: ToolCallAction,
        user_input: str,
        tool_summaries: list[str],
        summary: str,
    ) -> AgentResult:
        final = FinalAction(
            thought_summary=f"复用已执行工具结果：{action.tool_name}",
            answer=summary,
        )
        return self._finalize(user_id, session_id, step, final, user_input, tool_summaries)

    def _execute_tool_action(self, user_id: str, session_id: str, step: int, action: ToolCallAction) -> str:
        name = action.tool_name
        args = action.arguments
        self._write_trace(
            user_id,
            session_id,
            step,
            "tool_call",
            thought_summary=action.thought_summary,
            tool_name=name,
            arguments=args,
        )
        try:
            summary = self._invoke_tool(name, args, user_id, session_id)
        except ToolRegistryError as exc:
            self._write_trace(
                user_id,
                session_id,
                step,
                "tool_result",
                thought_summary=action.thought_summary,
                tool_name=name,
                arguments=args,
                status=TraceStatus.ERROR,
                error=exc.error_code.value,
            )
            self.session_manager.set_status(user_id, session_id, SessionStatus.ERROR)
            raise

        self._write_trace(
            user_id,
            session_id,
            step,
            "tool_result",
            thought_summary=action.thought_summary,
            tool_name=name,
            arguments=args,
            result_summary=summary,
        )
        self.session_manager.add_message(user_id, session_id, MessageRole.TOOL, summary)
        return summary

    def _finalize(
        self,
        user_id: str,
        session_id: str,
        step: int,
        action: FinalAction,
        user_input: str,
        tool_summaries: list[str],
    ) -> AgentResult:
        self._write_trace(
            user_id,
            session_id,
            step,
            "final",
            thought_summary=action.thought_summary,
            result_summary=action.answer,
        )
        self.session_manager.add_message(user_id, session_id, MessageRole.ASSISTANT, action.answer)
        self.session_manager.set_status(user_id, session_id, SessionStatus.COMPLETED)
        self._update_memory_after_turn(user_id, session_id, user_input, action.answer, tool_summaries)
        return AgentResult(answer=action.answer, session_status=SessionStatus.COMPLETED)

    def _update_memory_after_turn(
        self,
        user_id: str,
        session_id: str,
        user_input: str,
        assistant_answer: str,
        tool_summaries: list[str],
    ) -> None:
        if self.memory_manager is None:
            return
        try:
            self.memory_manager.update_from_turn(user_id, session_id, user_input, assistant_answer, tool_summaries)
        except Exception:
            return

    def _invoke_tool(self, name: str, args: dict[str, object], user_id: str, session_id: str) -> str:
        if self.tool_registry is None:
            raise ToolRegistryError(ErrorCode.UNKNOWN_TOOL, f"Unknown tool: {name}")
        result = self.tool_registry.execute(name, args, context={"user_id": user_id, "session_id": session_id})
        return str(result.get("summary", result))

    def _fallback_with_error(
        self,
        user_id: str,
        session_id: str,
        step: int,
        error_code: ErrorCode,
    ) -> AgentResult:
        self._write_trace(
            user_id,
            session_id,
            step,
            "fallback",
            status=TraceStatus.ERROR,
            error=error_code.value,
        )
        self.session_manager.set_status(user_id, session_id, SessionStatus.ERROR)
        if error_code in {
            ErrorCode.UNKNOWN_TOOL,
            ErrorCode.INVALID_TOOL_ARGUMENTS,
            ErrorCode.TOOL_TIMEOUT,
            ErrorCode.TOOL_EXECUTION_ERROR,
            ErrorCode.MAX_STEPS_EXCEEDED,
        }:
            answer = "当前工具调用失败，我已经停止继续执行。"
        else:
            answer = "暂时无法完成请求，请稍后重试或检查模型输出协议。"
        return AgentResult(answer=answer, session_status=SessionStatus.ERROR)

    def _write_trace(
        self,
        user_id: str,
        session_id: str,
        step: int,
        action_type: str,
        thought_summary: str = "",
        tool_name: str | None = None,
        arguments: dict[str, object] | None = None,
        result_summary: str | None = None,
        status: TraceStatus = TraceStatus.SUCCESS,
        error: str | None = None,
    ) -> None:
        if self.trace_logger is None:
            return
        self.trace_logger.write_trace(
            user_id=user_id,
            session_id=session_id,
            step=step,
            action_type=action_type,
            thought_summary=thought_summary,
            tool_name=tool_name,
            arguments=arguments or {},
            result_summary=result_summary,
            status=status,
            error=error,
        )
