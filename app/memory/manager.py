from __future__ import annotations

import json
from typing import Any

from app.contracts import utc_now_iso
from app.memory.extractor import HeuristicMemoryExtractor, MemoryExtractor
from app.memory.vector_store import NullVectorMemoryStore, VectorMemoryHit, VectorMemoryStore
from app.storage.sqlite_store import SQLiteStore


class MemoryManager:
    _ALLOWED_PROFILE_KEYS = {"preferred_language", "answer_style", "common_topics", "timezone"}
    _SENSITIVE_MARKERS = (
        "api key",
        "apikey",
        "secret",
        "token",
        "password",
        "passwd",
        "bearer ",
        "sk-",
        "密钥",
        "密码",
        "令牌",
        "私钥",
    )

    def __init__(
        self,
        store: SQLiteStore,
        vector_store: VectorMemoryStore | None = None,
        extractor: MemoryExtractor | None = None,
        retrieval_limit: int = 5,
    ) -> None:
        self.store = store
        self.vector_store = vector_store or NullVectorMemoryStore()
        self.extractor = extractor or HeuristicMemoryExtractor()
        self.retrieval_limit = retrieval_limit

    def upsert_profile(
        self,
        user_id: str,
        preferred_language: str | None = None,
        answer_style: str | None = None,
        common_topics: list[str] | None = None,
        timezone: str | None = None,
    ) -> None:
        existing = self.get_profile(user_id) or {}
        merged_topics = common_topics if common_topics is not None else existing.get("common_topics", [])
        now = utc_now_iso()
        self.store.execute(
            """
            INSERT INTO user_profiles (user_id, preferred_language, answer_style, common_topics, timezone, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                preferred_language = excluded.preferred_language,
                answer_style = excluded.answer_style,
                common_topics = excluded.common_topics,
                timezone = excluded.timezone,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                preferred_language if preferred_language is not None else existing.get("preferred_language"),
                answer_style if answer_style is not None else existing.get("answer_style"),
                json.dumps(merged_topics or [], ensure_ascii=False),
                timezone if timezone is not None else existing.get("timezone"),
                now,
            ),
        )

    def get_profile(self, user_id: str) -> dict[str, Any] | None:
        row = self.store.query_one("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,))
        if row is None:
            return None
        return {
            "user_id": row["user_id"],
            "preferred_language": row["preferred_language"],
            "answer_style": row["answer_style"],
            "common_topics": self._loads_list(row["common_topics"]),
            "timezone": row["timezone"],
        }

    def update_from_turn(
        self,
        user_id: str,
        session_id: str,
        user_input: str,
        assistant_answer: str,
        tool_summaries: list[str] | None = None,
    ) -> None:
        extraction = self.extractor.extract(user_input, assistant_answer, tool_summaries or [])
        profile_updates = self._sanitize_profile_updates(extraction.profile_updates)
        if profile_updates:
            self.upsert_profile(user_id, **profile_updates)
        for content in self._sanitize_semantic_memories(extraction.semantic_memories):
            self.add_semantic_memory(user_id, content, source_session_id=session_id, confidence=0.8)
        episodic_memories = self._sanitize_episodic_memories(extraction.episodic_memories)
        if not episodic_memories:
            fallback = HeuristicMemoryExtractor().extract(user_input, assistant_answer, tool_summaries or [])
            episodic_memories = self._sanitize_episodic_memories(fallback.episodic_memories)
        for memory in episodic_memories:
            self.add_episodic_memory(
                user_id=user_id,
                session_id=session_id,
                event_type=memory["event_type"],
                content=memory["content"],
                summary=memory["summary"],
                importance=memory["importance"],
            )

    def add_semantic_memory(
        self,
        user_id: str,
        content: str,
        source_session_id: str | None = None,
        confidence: float = 1.0,
    ) -> int:
        now = utc_now_iso()
        cursor = self.store.execute(
            """
            INSERT INTO semantic_memories (user_id, content, memory_type, source_session_id, confidence, created_at, updated_at)
            VALUES (?, ?, 'semantic', ?, ?, ?, ?)
            """,
            (user_id, content, source_session_id, confidence, now, now),
        )
        row_id = int(cursor.lastrowid)
        self._index_memory("semantic", row_id, user_id, content, {"source_session_id": source_session_id or ""})
        return row_id

    def add_episodic_memory(
        self,
        user_id: str,
        session_id: str,
        event_type: str,
        content: str,
        summary: str = "",
        importance: float = 0.5,
    ) -> int:
        cursor = self.store.execute(
            """
            INSERT INTO episodic_memories (user_id, session_id, event_type, content, summary, importance, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, session_id, event_type, content, summary, importance, utc_now_iso()),
        )
        row_id = int(cursor.lastrowid)
        self._index_memory(
            "episodic",
            row_id,
            user_id,
            content,
            {"session_id": session_id, "event_type": event_type, "importance": importance},
        )
        return row_id

    def should_retrieve(self, query: str) -> bool:
        triggers = ("之前", "上次", "继续", "还记得", "过去")
        return any(trigger in query for trigger in triggers)

    def retrieve(self, user_id: str, query: str) -> list[dict[str, str]]:
        try:
            vector_items = self._retrieve_from_vector(user_id, query)
            if vector_items:
                return vector_items
        except Exception:
            pass
        return self._retrieve_from_sqlite(user_id, query)

    def _sanitize_profile_updates(self, profile_updates: object) -> dict[str, object]:
        if not isinstance(profile_updates, dict):
            return {}
        cleaned: dict[str, object] = {}
        for key, value in profile_updates.items():
            if key not in self._ALLOWED_PROFILE_KEYS:
                continue
            if key == "common_topics":
                if not isinstance(value, list):
                    continue
                topics = [self._clip(item, 80) for item in value if isinstance(item, str)]
                topics = [topic for topic in topics if topic and not self._looks_sensitive(topic)]
                if topics:
                    cleaned[key] = topics
                continue
            if isinstance(value, str):
                compact = self._clip(value, 120)
                if compact and not self._looks_sensitive(compact):
                    cleaned[key] = compact
        return cleaned

    def _sanitize_semantic_memories(self, semantic_memories: object) -> list[str]:
        if not isinstance(semantic_memories, list):
            return []
        cleaned: list[str] = []
        for memory in semantic_memories:
            if not isinstance(memory, str):
                continue
            content = self._clip(memory, 300)
            if content and not self._looks_sensitive(content):
                cleaned.append(content)
        return cleaned

    def _sanitize_episodic_memories(self, episodic_memories: object) -> list[dict[str, Any]]:
        if not isinstance(episodic_memories, list):
            return []
        cleaned: list[dict[str, Any]] = []
        for memory in episodic_memories:
            if not isinstance(memory, dict):
                continue
            content = self._clip(memory.get("content", ""), 500)
            if not content or self._looks_sensitive(content):
                continue
            event_type = self._clip(memory.get("event_type", "turn_completed"), 80) or "turn_completed"
            summary = self._clip(memory.get("summary", ""), 160)
            cleaned.append(
                {
                    "event_type": event_type,
                    "content": content,
                    "summary": summary,
                    "importance": self._clamp_importance(memory.get("importance", 0.5)),
                }
            )
        return cleaned

    def _index_memory(
        self,
        memory_type: str,
        row_id: int,
        user_id: str,
        content: str,
        metadata: dict[str, object],
    ) -> None:
        embedding_id = f"{memory_type}:{row_id}"
        vector_metadata = {
            "memory_type": memory_type,
            "sqlite_id": row_id,
            "user_id": user_id,
            **metadata,
        }
        try:
            self.vector_store.upsert(embedding_id, content, vector_metadata)
        except Exception:
            return
        table = "semantic_memories" if memory_type == "semantic" else "episodic_memories"
        self.store.execute(f"UPDATE {table} SET embedding_id = ? WHERE id = ?", (embedding_id, row_id))

    def _retrieve_from_vector(self, user_id: str, query: str) -> list[dict[str, str]]:
        hits = self.vector_store.query(user_id, query, self.retrieval_limit)
        items: list[dict[str, str]] = []
        seen: set[tuple[str, int]] = set()
        for hit in hits:
            key = (hit.memory_type, hit.sqlite_id)
            if key in seen:
                continue
            seen.add(key)
            row = self._row_for_hit(user_id, hit)
            if row is None:
                continue
            items.append({"type": hit.memory_type, "content": row["content"]})
        return items

    def _row_for_hit(self, user_id: str, hit: VectorMemoryHit):
        if hit.memory_type == "semantic":
            return self.store.query_one(
                "SELECT * FROM semantic_memories WHERE user_id = ? AND id = ?",
                (user_id, hit.sqlite_id),
            )
        if hit.memory_type == "episodic":
            return self.store.query_one(
                "SELECT * FROM episodic_memories WHERE user_id = ? AND id = ?",
                (user_id, hit.sqlite_id),
            )
        return None

    def _retrieve_from_sqlite(self, user_id: str, query: str) -> list[dict[str, str]]:
        if not self.should_retrieve(query):
            return []
        semantic_rows = self.store.query_all(
            "SELECT content FROM semantic_memories WHERE user_id = ? ORDER BY id LIMIT ?",
            (user_id, self.retrieval_limit),
        )
        remaining = max(0, self.retrieval_limit - len(semantic_rows))
        episodic_rows = self.store.query_all(
            "SELECT content FROM episodic_memories WHERE user_id = ? ORDER BY id LIMIT ?",
            (user_id, remaining),
        )
        items = [{"type": "semantic", "content": row["content"]} for row in semantic_rows]
        items.extend({"type": "episodic", "content": row["content"]} for row in episodic_rows)
        return items

    def _looks_sensitive(self, text: str) -> bool:
        lowered = text.lower()
        return any(marker in lowered for marker in self._SENSITIVE_MARKERS)

    def _clamp_importance(self, value: object) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.5
        return min(1.0, max(0.0, number))

    def _clip(self, text: object, limit: int) -> str:
        compact = " ".join(str(text).split())
        return compact if len(compact) <= limit else compact[: limit - 1] + "…"

    def _loads_list(self, value: str) -> list[str]:
        try:
            loaded = json.loads(value)
        except Exception:
            return []
        return loaded if isinstance(loaded, list) else []
