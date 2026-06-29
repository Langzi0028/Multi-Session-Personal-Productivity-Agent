from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class LLMActionType(str, Enum):
    FINAL = "final"
    TOOL_CALL = "tool_call"


class SessionStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING_TOOL = "waiting_tool"
    WAITING_ASYNC_TOOL = "waiting_async_tool"
    COMPLETED = "completed"
    ERROR = "error"


class TodoStatus(str, Enum):
    PENDING = "pending"
    DONE = "done"


class AsyncJobStatus(str, Enum):
    SUBMITTED = "submitted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TraceStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    SYSTEM = "system"


class ErrorCode(str, Enum):
    LLM_API_ERROR = "LLM_API_ERROR"
    INVALID_LLM_OUTPUT = "INVALID_LLM_OUTPUT"
    UNKNOWN_TOOL = "UNKNOWN_TOOL"
    INVALID_TOOL_ARGUMENTS = "INVALID_TOOL_ARGUMENTS"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    TOOL_EXECUTION_ERROR = "TOOL_EXECUTION_ERROR"
    CONTEXT_TOO_LONG = "CONTEXT_TOO_LONG"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    DB_ERROR = "DB_ERROR"
    MAX_STEPS_EXCEEDED = "MAX_STEPS_EXCEEDED"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class FinalAction(BaseModel):
    type: LLMActionType = Field(default=LLMActionType.FINAL)
    thought_summary: str = ""
    answer: str


class ToolCallAction(BaseModel):
    type: LLMActionType = Field(default=LLMActionType.TOOL_CALL)
    thought_summary: str = ""
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class UserPublic(BaseModel):
    user_id: str
    username: str


class AuthRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    user: UserPublic


class SessionSummary(BaseModel):
    user_id: str
    session_id: str
    status: SessionStatus
    summary: str = ""
    created_at: str
    updated_at: str
    last_message_preview: str = ""
    message_count: int = 0


class Message(BaseModel):
    role: MessageRole
    content: str
    token_count: int = 0
    created_at: str = Field(default_factory=utc_now_iso)


class MessageRecord(BaseModel):
    id: int
    role: MessageRole
    content: str
    token_count: int = 0
    created_at: str


class TodoItem(BaseModel):
    id: int | None = None
    content: str
    status: TodoStatus = TodoStatus.PENDING
    due_time: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class ToolTrace(BaseModel):
    trace_id: str
    user_id: str
    session_id: str
    step: int
    action_type: str
    thought_summary: str = ""
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    result_summary: str | None = None
    latency_ms: int = 0
    status: TraceStatus = TraceStatus.SUCCESS
    error: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)


class SessionState(BaseModel):
    user_id: str
    session_id: str
    status: SessionStatus = SessionStatus.IDLE
    messages: list[Message] = Field(default_factory=list)
    session_summary: str = ""
    active_tasks: list[str] = Field(default_factory=list)
    todos: list[TodoItem] = Field(default_factory=list)
    recent_tool_results: list[dict[str, Any]] = Field(default_factory=list)
    tool_traces: list[ToolTrace] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
