from __future__ import annotations

import json
import uuid

from app.contracts import ToolTrace, TraceStatus, utc_now_iso
from app.storage.sqlite_store import SQLiteStore


class TraceLogger:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def write_trace(
        self,
        user_id: str,
        session_id: str,
        step: int,
        action_type: str,
        thought_summary: str = "",
        tool_name: str | None = None,
        arguments: dict[str, object] | None = None,
        result_summary: str | None = None,
        latency_ms: int = 0,
        status: TraceStatus = TraceStatus.SUCCESS,
        error: str | None = None,
    ) -> ToolTrace:
        trace = ToolTrace(
            trace_id=f"trace_{uuid.uuid4().hex[:12]}",
            user_id=user_id,
            session_id=session_id,
            step=step,
            action_type=action_type,
            thought_summary=thought_summary,
            tool_name=tool_name,
            arguments=arguments or {},
            result_summary=result_summary,
            latency_ms=latency_ms,
            status=status,
            error=error,
            created_at=utc_now_iso(),
        )
        self.store.execute(
            """
            INSERT INTO tool_traces (
                trace_id, user_id, session_id, step, action_type, thought_summary,
                tool_name, arguments_json, result_summary, latency_ms, status, error, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trace.trace_id,
                trace.user_id,
                trace.session_id,
                trace.step,
                trace.action_type,
                trace.thought_summary,
                trace.tool_name,
                json.dumps(trace.arguments, ensure_ascii=False),
                trace.result_summary,
                trace.latency_ms,
                trace.status.value,
                trace.error,
                trace.created_at,
            ),
        )
        return trace

    def list_traces(self, user_id: str, session_id: str) -> list[ToolTrace]:
        rows = self.store.query_all(
            "SELECT * FROM tool_traces WHERE user_id = ? AND session_id = ? ORDER BY id",
            (user_id, session_id),
        )
        return [
            ToolTrace(
                trace_id=row["trace_id"],
                user_id=row["user_id"],
                session_id=row["session_id"],
                step=row["step"],
                action_type=row["action_type"],
                thought_summary=row["thought_summary"],
                tool_name=row["tool_name"],
                arguments=json.loads(row["arguments_json"]),
                result_summary=row["result_summary"],
                latency_ms=row["latency_ms"],
                status=TraceStatus(row["status"]),
                error=row["error"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
