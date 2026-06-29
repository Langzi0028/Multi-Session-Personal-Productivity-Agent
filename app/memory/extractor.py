from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class MemoryExtraction:
    profile_updates: dict[str, object] = field(default_factory=dict)
    semantic_memories: list[str] = field(default_factory=list)
    episodic_memories: list[dict[str, object]] = field(default_factory=list)


class MemoryExtractor(Protocol):
    def extract(
        self,
        user_input: str,
        assistant_answer: str,
        tool_summaries: list[str] | None = None,
    ) -> MemoryExtraction:
        ...


class HeuristicMemoryExtractor:
    def extract(
        self,
        user_input: str,
        assistant_answer: str,
        tool_summaries: list[str] | None = None,
    ) -> MemoryExtraction:
        profile_updates: dict[str, object] = {}
        if "中文" in user_input and ("回答" in user_input or "偏好" in user_input or "用" in user_input):
            profile_updates["preferred_language"] = "中文"
        if "英文" in user_input or "English" in user_input:
            profile_updates["preferred_language"] = "English"
        if "简洁" in user_input or "直接" in user_input:
            profile_updates["answer_style"] = "简洁直接"
        if "详细" in user_input or "一步步" in user_input:
            profile_updates["answer_style"] = "详细"

        timezone = self._extract_timezone(user_input)
        if timezone:
            profile_updates["timezone"] = timezone

        semantic_memories = self._extract_semantic_memories(user_input)
        episodic_content = self._turn_summary(user_input, assistant_answer, tool_summaries or [])
        return MemoryExtraction(
            profile_updates=profile_updates,
            semantic_memories=semantic_memories,
            episodic_memories=[
                {
                    "event_type": "turn_completed",
                    "content": episodic_content,
                    "summary": self._clip(episodic_content, 120),
                    "importance": 0.5,
                }
            ],
        )

    def _extract_timezone(self, text: str) -> str | None:
        match = re.search(r"(?:我的)?时区是\s*([A-Za-z_]+/[A-Za-z_]+)", text)
        return match.group(1) if match else None

    def _extract_semantic_memories(self, text: str) -> list[str]:
        triggers = ("请记住", "记住", "我偏好", "我喜欢", "我正在", "我是", "我的目标是")
        if not any(trigger in text for trigger in triggers):
            return []
        cleaned = text.strip()
        if cleaned.startswith("请记住："):
            cleaned = cleaned.removeprefix("请记住：")
        elif cleaned.startswith("请记住:"):
            cleaned = cleaned.removeprefix("请记住:")
        elif cleaned.startswith("记住："):
            cleaned = cleaned.removeprefix("记住：")
        elif cleaned.startswith("记住:"):
            cleaned = cleaned.removeprefix("记住:")
        return [self._clip(cleaned, 200)] if cleaned else []

    def _turn_summary(self, user_input: str, assistant_answer: str, tool_summaries: list[str]) -> str:
        parts = [f"用户请求：{self._clip(user_input, 160)}", f"助手回复：{self._clip(assistant_answer, 160)}"]
        if tool_summaries:
            parts.append("工具结果：" + "；".join(self._clip(summary, 80) for summary in tool_summaries))
        return "；".join(parts)

    def _clip(self, text: str, limit: int) -> str:
        compact = " ".join(str(text).split())
        return compact if len(compact) <= limit else compact[: limit - 1] + "…"


class LLMMemoryExtractor:
    _ALLOWED_PROFILE_KEYS = {"preferred_language", "answer_style", "common_topics", "timezone"}
    _SENSITIVE_MARKERS = (
        "api key",
        "apikey",
        "secret",
        "token",
        "password",
        "passwd",
        "bearer ",
        "sk-",
        "密钥",
        "密码",
        "令牌",
        "私钥",
    )
    _SYSTEM_PROMPT = """
你是一个长期记忆抽取器，只负责从单轮对话中抽取明确、长期有效、非敏感的信息。
必须只返回 JSON 对象，不要 Markdown，不要解释。

输出结构：
{
  "profile_updates": {
    "preferred_language": string,
    "answer_style": string,
    "common_topics": string[],
    "timezone": string
  },
  "semantic_memories": string[],
  "episodic_memories": [
    {"event_type": string, "content": string, "summary": string, "importance": number}
  ]
}

规则：
- 只保存用户明确表达或对话强支持的长期事实。
- 不保存 API key、token、password、secret、私钥、密钥、凭据或私有连接信息。
- profile_updates 只能使用 preferred_language、answer_style、common_topics、timezone。
- semantic_memories 保存稳定事实或偏好。
- episodic_memories 保存本轮值得跨 session 召回的事件，importance 取 0 到 1。
- 没有可保存内容时返回空对象/空数组。
""".strip()

    def __init__(
        self,
        json_client,
        fallback: MemoryExtractor | None = None,
        model: str | None = None,
        timeout_seconds: float = 10,
        max_input_chars: int = 6000,
    ) -> None:
        self.json_client = json_client
        self.fallback = fallback or HeuristicMemoryExtractor()
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_input_chars = max_input_chars

    def extract(
        self,
        user_input: str,
        assistant_answer: str,
        tool_summaries: list[str] | None = None,
    ) -> MemoryExtraction:
        try:
            response = self.json_client.complete_json(
                self._SYSTEM_PROMPT,
                self._payload(user_input, assistant_answer, tool_summaries or []),
                model=self.model,
                timeout=self.timeout_seconds,
            )
            return self._normalize_response(response)
        except Exception:
            return self.fallback.extract(user_input, assistant_answer, tool_summaries or [])

    def _payload(self, user_input: str, assistant_answer: str, tool_summaries: list[str]) -> dict[str, object]:
        return {
            "user_input": self._clip(user_input, self.max_input_chars),
            "assistant_answer": self._clip(assistant_answer, self.max_input_chars),
            "tool_summaries": [self._clip(summary, 600) for summary in tool_summaries],
        }

    def _normalize_response(self, response: object) -> MemoryExtraction:
        if not isinstance(response, dict):
            raise ValueError("memory extraction response must be an object")

        profile_updates = response.get("profile_updates", {})
        semantic_memories = response.get("semantic_memories", [])
        episodic_memories = response.get("episodic_memories", [])
        if not isinstance(profile_updates, dict):
            raise ValueError("profile_updates must be an object")
        if not isinstance(semantic_memories, list):
            raise ValueError("semantic_memories must be a list")
        if not isinstance(episodic_memories, list):
            raise ValueError("episodic_memories must be a list")

        return MemoryExtraction(
            profile_updates=self._normalize_profile(profile_updates),
            semantic_memories=self._normalize_semantic_memories(semantic_memories),
            episodic_memories=self._normalize_episodic_memories(episodic_memories),
        )

    def _normalize_profile(self, profile_updates: dict[str, object]) -> dict[str, object]:
        cleaned: dict[str, object] = {}
        for key, value in profile_updates.items():
            if key not in self._ALLOWED_PROFILE_KEYS:
                continue
            if key == "common_topics":
                topics = [self._clip(item, 80) for item in value] if isinstance(value, list) else []
                topics = [item for item in topics if item and not self._looks_sensitive(item)]
                if topics:
                    cleaned[key] = topics
                continue
            if isinstance(value, str):
                compact = self._clip(value, 120)
                if compact and not self._looks_sensitive(compact):
                    cleaned[key] = compact
        return cleaned

    def _normalize_semantic_memories(self, semantic_memories: list[object]) -> list[str]:
        cleaned: list[str] = []
        for memory in semantic_memories:
            if not isinstance(memory, str):
                continue
            content = self._clip(memory, 300)
            if content and not self._looks_sensitive(content):
                cleaned.append(content)
        return cleaned

    def _normalize_episodic_memories(self, episodic_memories: list[object]) -> list[dict[str, object]]:
        cleaned: list[dict[str, object]] = []
        for memory in episodic_memories:
            if not isinstance(memory, dict):
                continue
            content = self._clip(str(memory.get("content", "")), 500)
            if not content or self._looks_sensitive(content):
                continue
            event_type = self._clip(str(memory.get("event_type") or "turn_completed"), 80)
            summary = self._clip(str(memory.get("summary") or content), 160)
            cleaned.append(
                {
                    "event_type": event_type or "turn_completed",
                    "content": content,
                    "summary": summary,
                    "importance": self._clamp_importance(memory.get("importance", 0.5)),
                }
            )
        return cleaned

    def _looks_sensitive(self, text: str) -> bool:
        lowered = text.lower()
        return any(marker in lowered for marker in self._SENSITIVE_MARKERS)

    def _clamp_importance(self, value: object) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.5
        return min(1.0, max(0.0, number))

    def _clip(self, text: object, limit: int) -> str:
        compact = " ".join(str(text).split())
        return compact if len(compact) <= limit else compact[: limit - 1] + "…"
