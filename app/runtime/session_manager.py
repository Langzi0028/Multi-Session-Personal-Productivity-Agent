from __future__ import annotations

import json
import uuid

from app.contracts import (
    Message,
    MessageRecord,
    MessageRole,
    SessionState,
    SessionStatus,
    SessionSummary,
    TodoItem,
    TodoStatus,
    utc_now_iso,
)
from app.storage.sqlite_store import SQLiteStore


class SessionManager:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def ensure_session(self, user_id: str, session_id: str) -> None:
        now = utc_now_iso()
        row = self.store.query_one(
            "SELECT id FROM sessions WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        )
        if row is None:
            self.store.execute(
                """
                INSERT INTO sessions (user_id, session_id, status, summary, created_at, updated_at)
                VALUES (?, ?, ?, '', ?, ?)
                """,
                (user_id, session_id, SessionStatus.IDLE.value, now, now),
            )

    def create_session(self, user_id: str) -> SessionSummary:
        session_id = f"session_{uuid.uuid4().hex[:16]}"
        self.ensure_session(user_id, session_id)
        summary = self.get_session_summary(user_id, session_id)
        if summary is None:
            raise RuntimeError("created session was not persisted")
        return summary

    def session_exists(self, user_id: str, session_id: str) -> bool:
        row = self.store.query_one(
            "SELECT id FROM sessions WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        )
        return row is not None

    def list_sessions(self, user_id: str) -> list[SessionSummary]:
        rows = self.store.query_all(
            """
            SELECT * FROM sessions
            WHERE user_id = ?
            ORDER BY updated_at DESC, id DESC
            """,
            (user_id,),
        )
        return [self._build_session_summary(row) for row in rows]

    def get_session_summary(self, user_id: str, session_id: str) -> SessionSummary | None:
        row = self.store.query_one(
            "SELECT * FROM sessions WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        )
        if row is None:
            return None
        return self._build_session_summary(row)

    def list_messages(self, user_id: str, session_id: str) -> list[MessageRecord]:
        rows = self.store.query_all(
            """
            SELECT * FROM messages
            WHERE user_id = ? AND session_id = ? AND role IN (?, ?)
            ORDER BY id
            """,
            (user_id, session_id, MessageRole.USER.value, MessageRole.ASSISTANT.value),
        )
        return [
            MessageRecord(
                id=row["id"],
                role=MessageRole(row["role"]),
                content=row["content"],
                token_count=row["token_count"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def set_status(self, user_id: str, session_id: str, status: SessionStatus) -> None:
        self.ensure_session(user_id, session_id)
        self.store.execute(
            "UPDATE sessions SET status = ?, updated_at = ? WHERE user_id = ? AND session_id = ?",
            (status.value, utc_now_iso(), user_id, session_id),
        )

    def add_message(self, user_id: str, session_id: str, role: MessageRole, content: str) -> None:
        self.ensure_session(user_id, session_id)
        self.store.execute(
            """
            INSERT INTO messages (user_id, session_id, role, content, token_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, session_id, role.value, content, len(content), utc_now_iso()),
        )

    def add_todo(self, user_id: str, session_id: str, content: str, due_time: str | None = None) -> TodoItem:
        self.ensure_session(user_id, session_id)
        now = utc_now_iso()
        cursor = self.store.execute(
            """
            INSERT INTO todos (user_id, session_id, content, status, due_time, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, session_id, content, TodoStatus.PENDING.value, due_time, now, now),
        )
        return TodoItem(id=cursor.lastrowid, content=content, due_time=due_time, created_at=now, updated_at=now)

    def list_todos(self, user_id: str, session_id: str) -> list[TodoItem]:
        rows = self.store.query_all(
            "SELECT * FROM todos WHERE user_id = ? AND session_id = ? ORDER BY id",
            (user_id, session_id),
        )
        return [
            TodoItem(
                id=row["id"],
                content=row["content"],
                status=TodoStatus(row["status"]),
                due_time=row["due_time"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def complete_todo(self, user_id: str, session_id: str, content: str) -> TodoItem | None:
        row = self.store.query_one(
            """
            SELECT * FROM todos
            WHERE user_id = ? AND session_id = ? AND content = ? AND status = ?
            ORDER BY id LIMIT 1
            """,
            (user_id, session_id, content, TodoStatus.PENDING.value),
        )
        if row is None:
            return None
        now = utc_now_iso()
        self.store.execute(
            "UPDATE todos SET status = ?, updated_at = ? WHERE id = ?",
            (TodoStatus.DONE.value, now, row["id"]),
        )
        return TodoItem(
            id=row["id"],
            content=row["content"],
            status=TodoStatus.DONE,
            due_time=row["due_time"],
            created_at=row["created_at"],
            updated_at=now,
        )

    def update_summary(self, user_id: str, session_id: str, summary: str) -> None:
        self.ensure_session(user_id, session_id)
        self.store.execute(
            "UPDATE sessions SET summary = ?, updated_at = ? WHERE user_id = ? AND session_id = ?",
            (summary, utc_now_iso(), user_id, session_id),
        )

    def set_recent_tool_results(self, user_id: str, session_id: str, results: list[dict[str, object]]) -> None:
        self.ensure_session(user_id, session_id)
        self.store.execute(
            "UPDATE sessions SET recent_tool_results_json = ?, updated_at = ? WHERE user_id = ? AND session_id = ?",
            (json.dumps(results, ensure_ascii=False), utc_now_iso(), user_id, session_id),
        )

    def get_state(self, user_id: str, session_id: str) -> SessionState:
        self.ensure_session(user_id, session_id)
        session = self.store.query_one(
            "SELECT * FROM sessions WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        )
        message_rows = self.store.query_all(
            "SELECT * FROM messages WHERE user_id = ? AND session_id = ? ORDER BY id",
            (user_id, session_id),
        )
        messages = [
            Message(
                role=MessageRole(row["role"]),
                content=row["content"],
                token_count=row["token_count"],
                created_at=row["created_at"],
            )
            for row in message_rows
        ]
        todos = self.list_todos(user_id, session_id)
        recent_tool_results = json.loads(session["recent_tool_results_json"])
        active_tasks = json.loads(session["active_tasks_json"])
        return SessionState(
            user_id=user_id,
            session_id=session_id,
            status=SessionStatus(session["status"]),
            messages=messages,
            session_summary=session["summary"],
            active_tasks=active_tasks,
            todos=todos,
            recent_tool_results=recent_tool_results,
            created_at=session["created_at"],
            updated_at=session["updated_at"],
        )

    def _build_session_summary(self, row) -> SessionSummary:
        message_count_row = self.store.query_one(
            """
            SELECT COUNT(*) AS count FROM messages
            WHERE user_id = ? AND session_id = ? AND role IN (?, ?)
            """,
            (row["user_id"], row["session_id"], MessageRole.USER.value, MessageRole.ASSISTANT.value),
        )
        preview_row = self.store.query_one(
            """
            SELECT content FROM messages
            WHERE user_id = ? AND session_id = ? AND role IN (?, ?)
            ORDER BY id DESC LIMIT 1
            """,
            (row["user_id"], row["session_id"], MessageRole.USER.value, MessageRole.ASSISTANT.value),
        )
        preview = preview_row["content"] if preview_row is not None else ""
        if len(preview) > 80:
            preview = f"{preview[:80]}…"
        return SessionSummary(
            user_id=row["user_id"],
            session_id=row["session_id"],
            status=SessionStatus(row["status"]),
            summary=row["summary"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_message_preview=preview,
            message_count=message_count_row["count"] if message_count_row is not None else 0,
        )
