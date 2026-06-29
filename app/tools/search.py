from __future__ import annotations

from typing import Any


class SearchTool:
    name = "search"
    description = "搜索资料的模拟工具。"
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词",
            }
        },
        "required": ["query"],
    }
    timeout = 3.0
    is_async = False
    permission = "none"

    def run(self, arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        query = str(arguments["query"])
        return {
            "query": query,
            "results": [f"{query} 的模拟搜索结果"],
            "summary": f"找到关于 {query} 的模拟搜索结果。",
        }
