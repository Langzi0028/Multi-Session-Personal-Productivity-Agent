from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError, create_model

from app.contracts import ErrorCode
from app.tools.base import Tool


class ToolRegistryError(ValueError):
    def __init__(self, error_code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ToolRegistryError(ErrorCode.INVALID_TOOL_ARGUMENTS, f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolRegistryError(ErrorCode.UNKNOWN_TOOL, f"Unknown tool: {name}") from exc

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters_schema,
            }
            for tool in self._tools.values()
        ]

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        tool = self.get(name)
        self._validate_arguments(tool, arguments)
        try:
            return tool.run(arguments, context=context)
        except ToolRegistryError:
            raise
        except Exception as exc:
            raise ToolRegistryError(ErrorCode.TOOL_EXECUTION_ERROR, str(exc)) from exc

    def _validate_arguments(self, tool: Tool, arguments: dict[str, Any]) -> None:
        schema = tool.parameters_schema
        required = set(schema.get("required", []))
        properties = schema.get("properties", {})
        missing = sorted(required - set(arguments.keys()))
        if missing:
            raise ToolRegistryError(
                ErrorCode.INVALID_TOOL_ARGUMENTS,
                f"Missing required arguments for {tool.name}: {', '.join(missing)}",
            )

        fields: dict[str, tuple[type[Any], Any]] = {}
        for name, spec in properties.items():
            field_type: type[Any] = str if spec.get("type") == "string" else Any
            default = ... if name in required else None
            fields[name] = (field_type, default)
        model: type[BaseModel] = create_model(f"{tool.name.title()}Arguments", **fields)
        try:
            model.model_validate(arguments)
        except ValidationError as exc:
            raise ToolRegistryError(ErrorCode.INVALID_TOOL_ARGUMENTS, str(exc)) from exc
