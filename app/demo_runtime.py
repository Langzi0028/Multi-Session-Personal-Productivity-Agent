from __future__ import annotations

from app.main import build_default_runtime
from app.runtime.agent_runtime import AgentRuntime


def build_manual_demo_runtime() -> AgentRuntime:
    return build_default_runtime(
        scripted_responses=[
            {
                "type": "tool_call",
                "thought_summary": "查询北京天气",
                "tool_name": "weather",
                "arguments": {"city": "北京"},
            },
            {
                "type": "tool_call",
                "thought_summary": "添加 window_1 待办",
                "tool_name": "todo",
                "arguments": {"action": "add", "content": "晚上 8 点带伞出门"},
            },
            {
                "type": "final",
                "thought_summary": "天气和待办已完成",
                "answer": "北京今天多云，下午可能有阵雨。已记录待办：晚上 8 点带伞出门。",
            },
            {
                "type": "tool_call",
                "thought_summary": "添加 window_2 待办",
                "tool_name": "todo",
                "arguments": {"action": "add", "content": "明天上午整理 README"},
            },
            {
                "type": "final",
                "thought_summary": "window_2 待办已完成",
                "answer": "已记录待办：明天上午整理 README。",
            },
        ]
    )
