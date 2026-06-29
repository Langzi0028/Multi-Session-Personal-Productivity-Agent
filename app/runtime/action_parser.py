from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.contracts import ErrorCode, FinalAction, LLMActionType, ToolCallAction


class ActionParserError(ValueError):
    def __init__(self, error_code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class ActionParser:
    def parse(self, raw_action: dict[str, Any]) -> FinalAction | ToolCallAction:
        if not isinstance(raw_action, dict):
            raise ActionParserError(ErrorCode.INVALID_LLM_OUTPUT, "LLM output must be an object")

        action_type = raw_action.get("type")
        try:
            if action_type == LLMActionType.FINAL.value:
                return FinalAction.model_validate(raw_action)
            if action_type == LLMActionType.TOOL_CALL.value:
                return ToolCallAction.model_validate(raw_action)
        except ValidationError as exc:
            raise ActionParserError(ErrorCode.INVALID_LLM_OUTPUT, str(exc)) from exc

        raise ActionParserError(ErrorCode.INVALID_LLM_OUTPUT, f"Unknown action type: {action_type}")
