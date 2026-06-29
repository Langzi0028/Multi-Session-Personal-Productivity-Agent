from __future__ import annotations


class ScriptedLLM:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self._responses = list(responses)
        self.calls: list[list[dict[str, object]]] = []

    @property
    def model(self) -> str:
        return "scripted"

    def complete(self, context: list[dict[str, object]]) -> dict[str, object]:
        self.calls.append(context)
        return self._pop_response()

    def _pop_response(self) -> dict[str, object]:
        if not self._responses:
            return {
                "type": "final",
                "thought_summary": "no scripted response left",
                "answer": "没有更多响应。",
            }
        return self._responses.pop(0)
