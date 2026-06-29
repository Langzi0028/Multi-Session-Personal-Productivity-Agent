from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class VectorMemoryHit:
    memory_type: str
    embedding_id: str
    sqlite_id: int
    score: float
    content: str
    metadata: dict[str, object] = field(default_factory=dict)


class VectorMemoryStore(Protocol):
    def upsert(self, memory_id: str, content: str, metadata: dict[str, object]) -> None:
        ...

    def query(self, user_id: str, query: str, limit: int) -> list[VectorMemoryHit]:
        ...


class NullVectorMemoryStore:
    def upsert(self, memory_id: str, content: str, metadata: dict[str, object]) -> None:
        return None

    def query(self, user_id: str, query: str, limit: int) -> list[VectorMemoryHit]:
        return []


class ChromaVectorMemoryStore:
    def __init__(self, path: str, collection_name: str = "long_term_memory") -> None:
        import chromadb

        self.client = chromadb.PersistentClient(path=path)
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def upsert(self, memory_id: str, content: str, metadata: dict[str, object]) -> None:
        self.collection.upsert(
            ids=[memory_id],
            documents=[content],
            metadatas=[metadata],
        )

    def query(self, user_id: str, query: str, limit: int) -> list[VectorMemoryHit]:
        results = self.collection.query(
            query_texts=[query],
            n_results=limit,
            where={"user_id": user_id},
        )
        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0] if results.get("distances") else [0.0] * len(ids)
        hits: list[VectorMemoryHit] = []
        for index, memory_id in enumerate(ids):
            metadata = dict(metadatas[index] or {})
            hits.append(
                VectorMemoryHit(
                    memory_type=str(metadata.get("memory_type", "")),
                    embedding_id=str(memory_id),
                    sqlite_id=int(metadata.get("sqlite_id", 0)),
                    score=float(distances[index]),
                    content=str(documents[index]),
                    metadata=metadata,
                )
            )
        return hits
