from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class SQLiteStore:
    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    @property
    def connection(self) -> sqlite3.Connection:
        return self._connection

    def init_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS auth_tokens (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                active_tasks_json TEXT NOT NULL DEFAULT '[]',
                recent_tool_results_json TEXT NOT NULL DEFAULT '[]',
                event_queue_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, session_id)
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                token_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                content TEXT NOT NULL,
                status TEXT NOT NULL,
                due_time TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tool_traces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                step INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                thought_summary TEXT NOT NULL DEFAULT '',
                tool_name TEXT,
                arguments_json TEXT NOT NULL DEFAULT '{}',
                result_summary TEXT,
                latency_ms INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                error TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS async_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL UNIQUE,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                arguments_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL,
                result_json TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                preferred_language TEXT,
                answer_style TEXT,
                common_topics TEXT NOT NULL DEFAULT '[]',
                timezone TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_profile_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 1.0,
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS semantic_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                content TEXT NOT NULL,
                memory_type TEXT NOT NULL DEFAULT 'semantic',
                embedding_id TEXT,
                source_session_id TEXT,
                confidence REAL NOT NULL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS episodic_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                content TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                embedding_id TEXT,
                importance REAL NOT NULL DEFAULT 0.5,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_auth_tokens_user_id ON auth_tokens(user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_user_updated ON sessions(user_id, updated_at);
            CREATE INDEX IF NOT EXISTS idx_messages_user_session_id ON messages(user_id, session_id, id);
            CREATE INDEX IF NOT EXISTS idx_semantic_memories_user_id ON semantic_memories(user_id);
            CREATE INDEX IF NOT EXISTS idx_semantic_memories_embedding_id ON semantic_memories(embedding_id);
            CREATE INDEX IF NOT EXISTS idx_episodic_memories_user_id ON episodic_memories(user_id);
            CREATE INDEX IF NOT EXISTS idx_episodic_memories_session_id ON episodic_memories(session_id);
            CREATE INDEX IF NOT EXISTS idx_episodic_memories_embedding_id ON episodic_memories(embedding_id);
            """
        )
        self._connection.commit()

    def list_table_names(self) -> list[str]:
        rows = self._connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [row["name"] for row in rows]

    def execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        cursor = self._connection.execute(sql, parameters)
        self._connection.commit()
        return cursor

    def query_all(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        return list(self._connection.execute(sql, parameters).fetchall())

    def query_one(self, sql: str, parameters: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        return self._connection.execute(sql, parameters).fetchone()
