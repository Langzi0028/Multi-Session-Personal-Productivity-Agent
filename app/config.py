from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    openai_api_base: str | None
    openai_api_key: str | None = field(repr=False)
    openai_model: str
    sqlite_db_path: str
    vector_store_path: str
    max_agent_steps: int
    memory_extractor_mode: str
    memory_extractor_timeout_seconds: float
    memory_extractor_model: str | None
    memory_extractor_max_input_chars: int
    context_summarizer_mode: str
    context_summarizer_timeout_seconds: float
    context_summarizer_model: str | None
    context_summarizer_max_input_chars: int
    context_summarizer_max_summary_chars: int


def load_dotenv(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def get_settings() -> Settings:
    load_dotenv()
    memory_extractor_model = os.getenv("MEMORY_EXTRACTOR_MODEL") or None
    context_summarizer_model = os.getenv("CONTEXT_SUMMARIZER_MODEL") or None
    return Settings(
        openai_api_base=os.getenv("OPENAI_API_BASE"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        sqlite_db_path=os.getenv("SQLITE_DB_PATH", "./agent_runtime.db"),
        vector_store_path=os.getenv("VECTOR_STORE_PATH", "./vector_store"),
        max_agent_steps=int(os.getenv("MAX_AGENT_STEPS", "5")),
        memory_extractor_mode=os.getenv("MEMORY_EXTRACTOR_MODE", "llm"),
        memory_extractor_timeout_seconds=float(os.getenv("MEMORY_EXTRACTOR_TIMEOUT_SECONDS", "10")),
        memory_extractor_model=memory_extractor_model,
        memory_extractor_max_input_chars=int(os.getenv("MEMORY_EXTRACTOR_MAX_INPUT_CHARS", "6000")),
        context_summarizer_mode=os.getenv("CONTEXT_SUMMARIZER_MODE", "llm"),
        context_summarizer_timeout_seconds=float(os.getenv("CONTEXT_SUMMARIZER_TIMEOUT_SECONDS", "10")),
        context_summarizer_model=context_summarizer_model,
        context_summarizer_max_input_chars=int(os.getenv("CONTEXT_SUMMARIZER_MAX_INPUT_CHARS", "6000")),
        context_summarizer_max_summary_chars=int(os.getenv("CONTEXT_SUMMARIZER_MAX_SUMMARY_CHARS", "2000")),
    )
