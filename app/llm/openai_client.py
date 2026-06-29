from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import Settings
from app.contracts import ErrorCode
from app.runtime.action_parser import ActionParserError


class OpenAICompatibleClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_base:
            raise ValueError("OPENAI_API_BASE is required for OpenAICompatibleClient")
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAICompatibleClient")
        self.api_base = settings.openai_api_base.rstrip("/")
        self.api_key = settings.openai_api_key
        self.model = settings.openai_model

    def complete(self, context: list[dict[str, object]]) -> dict[str, object]:
        try:
            return self.complete_json(
                (
                    "你是一个 Agent Runtime 决策器。必须只输出 JSON 对象，"
                    "格式为 {type: 'final', thought_summary: string, answer: string} "
                    "或 {type: 'tool_call', thought_summary: string, tool_name: string, arguments: object}。"
                    "你会在上下文中收到 available_tools，里面列出当前已注册工具的 name、description 和 parameters。"
                    "你还会收到 current_turn_events，它按顺序记录当前用户请求、本轮 assistant_action tool_call 和 tool_result。"
                    "current_user_input 和 current_turn_events 中的最新 user 内容是当前必须处理的请求；recent_messages、relevant_long_term_memory、session_summary 只能作为背景，不能覆盖当前请求。"
                    "生成 tool_call 时，工具参数必须来自当前用户请求或当前轮 tool_result，不能从历史消息或长期记忆中拿旧关键词替代当前请求。"
                    "当用户询问偏好、已记住的信息、项目背景、长期事实时，必须优先使用 user_profile 和 relevant_long_term_memory 中 type 为 semantic 的 semantic_memory 回答。"
                    "当用户询问之前、上次、过去、问过什么、做过什么、聊过什么时，必须优先使用 relevant_long_term_memory 中 type 为 episodic 的 episodic_memory 回答。"
                    "注意 semantic_memory 是长期稳定事实，episodic_memory 是历史事件，todos 是当前 session 待办；不要把 episodic_memory 当成当前 session 的 todo。"
                    "如果用户请求能由 available_tools 中任一工具完成，并且 current_turn_events 中还没有可用 tool_result，必须先输出 tool_call，"
                    "并按该工具 parameters 提供 arguments。工具结果会作为 tool_result 加入下一轮 current_turn_events。"
                    "当 current_turn_events 最后一项或 recent_tool_results 已经包含能回答当前请求的工具结果时，必须输出 final，不要重复调用同一个工具。"
                    "当 available_tools 中已有可用工具能处理请求时，不能直接回答无法获取或建议用户自行查询。"
                ),
                context,
                model=self.model,
                timeout=60,
            )
        except Exception as exc:
            raise ActionParserError(ErrorCode.LLM_API_ERROR, "LLM API call failed") from exc

    def complete_json(
        self,
        system_prompt: str,
        payload: object,
        model: str | None = None,
        timeout: float = 60,
    ) -> dict[str, object]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        response = httpx.post(
            f"{self.api_base}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": model or self.model, "messages": messages, "temperature": 0},
            timeout=timeout,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        parsed: Any = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("LLM JSON response must be an object")
        return parsed
