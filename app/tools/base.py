from __future__ import annotations

from typing import Any, Protocol


class Tool(Protocol):
    name: str
    description: str
    parameters_schema: dict[str, Any]
    timeout: float
    is_async: bool
    permission: str

    def run(self, arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute the tool and return a JSON-like result."""
