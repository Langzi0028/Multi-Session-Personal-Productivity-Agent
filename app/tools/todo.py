from __future__ import annotations

from typing import Any

from app.runtime.session_manager import SessionManager


class TodoTool:
    name = "todo"
    description = "为当前 session 添加、查询或完成待办事项。"
    parameters_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["add", "list", "done"]},
            "content": {"type": "string"},
            "due_time": {"type": "string"},
        },
        "required": ["action"],
    }
    timeout = 3.0
    is_async = False
    permission = "none"

    def __init__(self, session_manager: SessionManager) -> None:
        self.session_manager = session_manager

    def run(self, arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        if context is None:
            raise ValueError("todo tool requires user/session context")
        user_id = str(context["user_id"])
        session_id = str(context["session_id"])
        action = arguments["action"]

        if action == "add":
            content = str(arguments.get("content", "")).strip()
            if not content:
                raise ValueError("todo add requires content")
            todo = self.session_manager.add_todo(user_id, session_id, content, arguments.get("due_time"))
            return {"todo_id": todo.id, "content": todo.content, "summary": f"添加成功：{todo.content}"}

        if action == "list":
            todos = self.session_manager.list_todos(user_id, session_id)
            summary = "；".join(f"{todo.id}. {todo.content} [{todo.status.value}]" for todo in todos) or "暂无待办"
            return {"todos": [todo.model_dump() for todo in todos], "summary": summary}

        if action == "done":
            content = str(arguments.get("content", "")).strip()
            if not content:
                raise ValueError("todo done requires content")
            todo = self.session_manager.complete_todo(user_id, session_id, content)
            if todo is None:
                raise ValueError("todo not found")
            return {"todo_id": todo.id, "content": todo.content, "summary": f"已完成：{todo.content}"}

        raise ValueError(f"unsupported todo action: {action}")
