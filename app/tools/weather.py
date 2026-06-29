from __future__ import annotations

from typing import Any


class WeatherTool:
    name = "weather"
    description = "查询指定城市的天气。"
    parameters_schema = {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市名，例如 北京、上海、首尔",
            }
        },
        "required": ["city"],
    }
    timeout = 3.0
    is_async = False
    permission = "none"

    def run(self, arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        city = str(arguments["city"])
        if city == "北京":
            weather = "北京今天多云，下午可能有阵雨。"
        else:
            weather = f"{city}今天天气晴朗。"
        return {"city": city, "weather": weather, "summary": weather}
