from __future__ import annotations

from typing import Any

from app.runtime.async_manager import AsyncManager


class LongSearchTool:
    name = "long_search"
    description = "模拟耗时搜索任务，异步提交并返回 job_id。"
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"}
        },
        "required": ["query"],
    }
    timeout = 3.0
    is_async = True
    permission = "none"

    def __init__(self, async_manager: AsyncManager) -> None:
        self.async_manager = async_manager

    def run(self, arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, str]:
        if context is None:
            raise ValueError("long_search requires user/session context")
        return self.async_manager.submit_job(
            user_id=str(context["user_id"]),
            session_id=str(context["session_id"]),
            tool_name=self.name,
            arguments=arguments,
        )
