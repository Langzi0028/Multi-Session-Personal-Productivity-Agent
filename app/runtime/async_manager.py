from __future__ import annotations

import json
import uuid

from app.contracts import AsyncJobStatus, SessionStatus, TraceStatus, utc_now_iso
from app.runtime.session_manager import SessionManager
from app.runtime.trace_logger import TraceLogger
from app.storage.sqlite_store import SQLiteStore


class AsyncManager:
    def __init__(self, store: SQLiteStore, session_manager: SessionManager, trace_logger: TraceLogger) -> None:
        self.store = store
        self.session_manager = session_manager
        self.trace_logger = trace_logger

    def submit_job(self, user_id: str, session_id: str, tool_name: str, arguments: dict[str, object]) -> dict[str, str]:
        self.session_manager.ensure_session(user_id, session_id)
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        now = utc_now_iso()
        self.store.execute(
            """
            INSERT INTO async_jobs (job_id, user_id, session_id, tool_name, arguments_json, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, user_id, session_id, tool_name, json.dumps(arguments, ensure_ascii=False), AsyncJobStatus.SUBMITTED.value, now, now),
        )
        self.session_manager.set_status(user_id, session_id, SessionStatus.WAITING_ASYNC_TOOL)
        self.trace_logger.write_trace(
            user_id=user_id,
            session_id=session_id,
            step=1,
            action_type="async_tool_submitted",
            tool_name=tool_name,
            arguments=arguments,
            result_summary=job_id,
        )
        return {"status": AsyncJobStatus.SUBMITTED.value, "job_id": job_id, "message": "任务已提交，完成后会写回当前 session。"}

    def get_job(self, job_id: str) -> dict[str, object]:
        row = self.store.query_one("SELECT * FROM async_jobs WHERE job_id = ?", (job_id,))
        if row is None:
            raise ValueError("job not found")
        return {
            "job_id": row["job_id"],
            "user_id": row["user_id"],
            "session_id": row["session_id"],
            "tool_name": row["tool_name"],
            "arguments": json.loads(row["arguments_json"]),
            "status": row["status"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
        }

    def complete_job(self, job_id: str, result: dict[str, object]) -> None:
        job = self.get_job(job_id)
        now = utc_now_iso()
        self.store.execute(
            "UPDATE async_jobs SET status = ?, result_json = ?, updated_at = ? WHERE job_id = ?",
            (AsyncJobStatus.COMPLETED.value, json.dumps(result, ensure_ascii=False), now, job_id),
        )
        session_result = {"job_id": job_id, "summary": str(result.get("summary", result))}
        self.session_manager.set_recent_tool_results(job["user_id"], job["session_id"], [session_result])
        self.session_manager.set_status(job["user_id"], job["session_id"], SessionStatus.COMPLETED)
        self.trace_logger.write_trace(
            user_id=str(job["user_id"]),
            session_id=str(job["session_id"]),
            step=1,
            action_type="async_tool_completed",
            tool_name=str(job["tool_name"]),
            result_summary=session_result["summary"],
            status=TraceStatus.SUCCESS,
        )

    def mark_running(self, user_id: str, session_id: str) -> None:
        self.session_manager.set_status(user_id, session_id, SessionStatus.RUNNING)

    def try_acquire_writer(self, user_id: str, session_id: str) -> bool:
        state = self.session_manager.get_state(user_id, session_id)
        return state.status not in {SessionStatus.RUNNING, SessionStatus.WAITING_ASYNC_TOOL}

    def enqueue_event(self, user_id: str, session_id: str, event: dict[str, object]) -> None:
        self.session_manager.ensure_session(user_id, session_id)
        row = self.store.query_one(
            "SELECT event_queue_json FROM sessions WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        )
        events = json.loads(row["event_queue_json"])
        events.append(event)
        self.store.execute(
            "UPDATE sessions SET event_queue_json = ?, updated_at = ? WHERE user_id = ? AND session_id = ?",
            (json.dumps(events, ensure_ascii=False), utc_now_iso(), user_id, session_id),
        )

    def drain_events(self, user_id: str, session_id: str) -> list[dict[str, object]]:
        row = self.store.query_one(
            "SELECT event_queue_json FROM sessions WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        )
        events = json.loads(row["event_queue_json"])
        self.store.execute(
            "UPDATE sessions SET event_queue_json = '[]', updated_at = ? WHERE user_id = ? AND session_id = ?",
            (utc_now_iso(), user_id, session_id),
        )
        return sorted(events, key=lambda event: 0 if event.get("type") == "CancelEvent" else 1)
