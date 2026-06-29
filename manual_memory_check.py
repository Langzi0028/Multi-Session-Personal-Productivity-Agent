from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.config import load_dotenv


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_MESSAGE = "请记住：我偏好中文简洁回答，我正在准备 Agent 开发岗笔试。请直接回复已记住。"
DEFAULT_EXPECTED_TEXT = "Agent 开发岗笔试"


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def build_checks(
    health_ok: bool,
    create_ok: bool,
    message_payload: dict[str, Any],
    trace_payload: dict[str, Any],
    profile: dict[str, Any] | None,
    semantic_rows: list[dict[str, Any]],
    episodic_rows: list[dict[str, Any]],
    expected_text: str,
    session_id: str,
) -> list[Check]:
    traces = trace_payload.get("traces", []) if isinstance(trace_payload, dict) else []
    action_types = [trace.get("action_type") for trace in traces if isinstance(trace, dict)]
    answer = str(message_payload.get("answer", "")) if isinstance(message_payload, dict) else ""
    status = message_payload.get("session_status") if isinstance(message_payload, dict) else None

    semantic_ok = any(expected_text in str(row.get("content", "")) for row in semantic_rows)
    episodic_ok = any(
        row.get("session_id") == session_id and str(row.get("content", "")) for row in episodic_rows
    )
    profile_ok = bool(
        profile
        and (
            profile.get("preferred_language")
            or profile.get("answer_style")
            or profile.get("common_topics")
            or profile.get("timezone")
        )
    )

    return [
        Check("health endpoint", health_ok, "GET /health returned ok" if health_ok else "GET /health failed"),
        Check("session create", create_ok, "POST /sessions returned 200" if create_ok else "POST /sessions failed"),
        Check(
            "message completed",
            status == "completed" and bool(answer),
            f"session_status={status!r}, answer_length={len(answer)}",
        ),
        Check(
            "trace has final action",
            "final" in action_types,
            f"action_types={action_types}",
        ),
        Check(
            "trace has no memory extraction event",
            all("memory" not in str(action_type) for action_type in action_types),
            f"action_types={action_types}",
        ),
        Check(
            "profile memory",
            profile_ok,
            f"profile={profile}" if profile else "profile row not found",
        ),
        Check(
            "semantic memory",
            semantic_ok,
            f"expected substring={expected_text!r}, rows={len(semantic_rows)}",
        ),
        Check(
            "episodic memory",
            episodic_ok,
            f"session_id={session_id!r}, rows={len(episodic_rows)}",
        ),
    ]


def main() -> int:
    args = parse_args()
    load_dotenv(args.env_file)
    db_path = args.db_path or os.getenv("SQLITE_DB_PATH", "./agent_runtime.db")
    username = args.username or f"manual-memory-{uuid.uuid4().hex[:8]}"
    password = args.password
    user_id = ""
    session_id = ""

    print("Manual LLM memory check")
    print(f"- base_url: {args.base_url}")
    print(f"- db_path: {db_path}")
    print(f"- username: {username}")
    print(f"- expected_text: {args.expected_text}")
    print()

    health_ok, create_ok = False, False
    message_payload: dict[str, Any] = {}
    trace_payload: dict[str, Any] = {}

    try:
        with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=args.timeout) as client:
            health_ok = client.get("/health").status_code == 200
            register_response = client.post(
                "/auth/register",
                json={"username": username, "password": password},
            )
            auth_payload = _json_or_error(register_response)
            token = str(auth_payload.get("token", ""))
            user = auth_payload.get("user", {}) if isinstance(auth_payload.get("user"), dict) else {}
            user_id = str(user.get("user_id", ""))
            headers = {"Authorization": f"Bearer {token}"}
            create_response = client.post("/sessions", headers=headers, json={})
            create_payload = _json_or_error(create_response)
            session = create_payload.get("session", {}) if isinstance(create_payload.get("session"), dict) else {}
            session_id = str(session.get("session_id", ""))
            create_ok = create_response.status_code == 201 and bool(session_id)
            message_response = client.post(
                f"/sessions/{session_id}/messages",
                headers=headers,
                json={"content": args.message},
            )
            message_payload = _json_or_error(message_response)
            trace_response = client.get(f"/sessions/{session_id}/trace", headers=headers)
            trace_payload = _json_or_error(trace_response)
    except Exception as exc:
        print(f"[FAIL] HTTP request failed: {exc}")
        print("请先启动服务：python start_server.py")
        return 1

    if db_path == ":memory:":
        print("[FAIL] SQLITE_DB_PATH=:memory: 时，独立脚本无法读取服务进程内存数据库。")
        print("请把 .env 的 SQLITE_DB_PATH 改成文件路径，例如 ./agent_runtime.db，然后重启服务。")
        return 1

    try:
        profile, semantic_rows, episodic_rows = load_memory_rows(db_path, user_id, session_id)
    except Exception as exc:
        print(f"[FAIL] SQLite read failed: {exc}")
        return 1

    checks = build_checks(
        health_ok=health_ok,
        create_ok=create_ok,
        message_payload=message_payload,
        trace_payload=trace_payload,
        profile=profile,
        semantic_rows=semantic_rows,
        episodic_rows=episodic_rows,
        expected_text=args.expected_text,
        session_id=session_id,
    )
    print_checks(checks)
    print_memory_debug(profile, semantic_rows, episodic_rows)
    return 0 if all(check.ok for check in checks) else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send one request and verify LLM memory extraction wrote SQLite rows.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Running FastAPI base URL.")
    parser.add_argument("--env-file", default=".env", help="Path to .env used by the server.")
    parser.add_argument("--db-path", default=None, help="SQLite DB path. Defaults to SQLITE_DB_PATH from .env.")
    parser.add_argument("--username", default=None, help="Optional fixed username. Defaults to a unique manual user.")
    parser.add_argument("--password", default="password123", help="Password used for the temporary manual user.")
    parser.add_argument("--message", default=DEFAULT_MESSAGE, help="Message sent to POST /messages.")
    parser.add_argument("--expected-text", default=DEFAULT_EXPECTED_TEXT, help="Substring expected in semantic memory.")
    parser.add_argument("--timeout", type=float, default=120, help="HTTP timeout seconds for real LLM calls.")
    return parser.parse_args()


def _json_or_error(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception:
        payload = {"status_code": response.status_code, "text": response.text}
    if isinstance(payload, dict):
        payload.setdefault("_status_code", response.status_code)
        return payload
    return {"_status_code": response.status_code, "payload": payload}


def load_memory_rows(
    db_path: str,
    user_id: str,
    session_id: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    db_file = Path(db_path)
    if not db_file.exists():
        raise FileNotFoundError(f"SQLite DB not found: {db_file}")
    connection = sqlite3.connect(db_file)
    connection.row_factory = sqlite3.Row
    try:
        profile_row = connection.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)).fetchone()
        semantic_rows = connection.execute(
            "SELECT * FROM semantic_memories WHERE user_id = ? AND source_session_id = ? ORDER BY id",
            (user_id, session_id),
        ).fetchall()
        episodic_rows = connection.execute(
            "SELECT * FROM episodic_memories WHERE user_id = ? AND session_id = ? ORDER BY id",
            (user_id, session_id),
        ).fetchall()
    finally:
        connection.close()
    return _row_to_dict(profile_row), [_row_to_dict(row) for row in semantic_rows], [_row_to_dict(row) for row in episodic_rows]


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def print_checks(checks: list[Check]) -> None:
    print("Check result:")
    for check in checks:
        label = "PASS" if check.ok else "FAIL"
        print(f"[{label}] {check.name}: {check.detail}")
    print()


def print_memory_debug(
    profile: dict[str, Any] | None,
    semantic_rows: list[dict[str, Any]],
    episodic_rows: list[dict[str, Any]],
) -> None:
    print("SQLite memory rows:")
    print(f"- profile: {profile}")
    print(f"- semantic rows: {len(semantic_rows)}")
    for row in semantic_rows:
        print(f"  - id={row.get('id')} embedding_id={row.get('embedding_id')} content={row.get('content')}")
    print(f"- episodic rows: {len(episodic_rows)}")
    for row in episodic_rows:
        print(f"  - id={row.get('id')} embedding_id={row.get('embedding_id')} content={row.get('content')}")


if __name__ == "__main__":
    sys.exit(main())
