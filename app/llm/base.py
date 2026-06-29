from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    def complete(self, context: list[dict[str, object]]) -> dict[str, object]:
        """Return one JSON-like LLM action."""
