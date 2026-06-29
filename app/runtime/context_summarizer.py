from __future__ import annotations

from typing import Protocol

from app.contracts import Message


class ContextSummarizer(Protocol):
    def summarize(self, existing_summary: str, old_messages: list[Message]) -> str:
        ...


class RuleBasedContextSummarizer:
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

    def summarize(self, existing_summary: str, old_messages: list[Message]) -> str:
        old_summary = "\n".join(self._message_line(message) for message in old_messages)
        old_summary = old_summary.strip()
        if not old_summary:
            return existing_summary.strip()
        existing = existing_summary.strip()
        return f"{existing}\n{old_summary}".strip() if existing else old_summary

    def _message_line(self, message: Message) -> str:
        content = "[已省略敏感内容]" if self._looks_sensitive(message.content) else message.content
        return f"{message.role.value}: {content}"

    def _looks_sensitive(self, text: str) -> bool:
        lowered = text.lower()
        return any(marker in lowered for marker in self._SENSITIVE_MARKERS)


class LLMContextSummarizer:
    _SYSTEM_PROMPT = (
        "你是一个 session 上下文压缩器。必须只输出 JSON 对象，不要 Markdown，不要解释。"
        "输出格式为 {\"summary\": string}。"
        "你会收到 existing_summary 和即将离开 recent_messages 窗口的旧 messages。"
        "请生成更新后的完整 session_summary，用于后续对话上下文。"
        "保留：用户目标、偏好、项目背景、待办线索、工具结果、关键事实、未完成事项、重要约束。"
        "压缩时要去重，不要重复 existing_summary 已经表达过的信息。"
        "不要保存 API key、token、password、secret、私钥、密钥、凭据或私有连接信息。"
        "如果没有值得保留的信息，返回空字符串。"
    )

    def __init__(
        self,
        json_client,
        fallback: ContextSummarizer | None = None,
        model: str | None = None,
        timeout_seconds: float = 10,
        max_input_chars: int = 6000,
        max_summary_chars: int = 2000,
    ) -> None:
        self.json_client = json_client
        self.fallback = fallback or RuleBasedContextSummarizer()
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_input_chars = max_input_chars
        self.max_summary_chars = max_summary_chars

    def summarize(self, existing_summary: str, old_messages: list[Message]) -> str:
        try:
            response = self.json_client.complete_json(
                self._SYSTEM_PROMPT,
                self._payload(existing_summary, old_messages),
                model=self.model,
                timeout=self.timeout_seconds,
            )
            summary = response.get("summary", "")
            if not isinstance(summary, str):
                raise ValueError("summary must be a string")
            return self._clip(summary.strip(), self.max_summary_chars)
        except Exception:
            return self.fallback.summarize(existing_summary, old_messages)

    def _payload(self, existing_summary: str, old_messages: list[Message]) -> dict[str, object]:
        messages: list[dict[str, str]] = []
        used_chars = len(existing_summary)
        for message in old_messages:
            content = message.content
            used_chars += len(content)
            if used_chars > self.max_input_chars:
                remaining = max(0, self.max_input_chars - (used_chars - len(content)))
                if remaining <= 0:
                    break
                content = self._clip(content, remaining)
            messages.append({"role": message.role.value, "content": content})
        return {"existing_summary": existing_summary, "messages": messages}

    def _clip(self, text: str, limit: int) -> str:
        if limit <= 0:
            return ""
        return text if len(text) <= limit else text[: limit - 1] + "…"
