from app.config import get_settings, load_dotenv
from app.llm.openai_client import OpenAICompatibleClient
from app.main import build_default_runtime, start_api


def test_load_dotenv_and_build_real_runtime_without_exposing_key(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENAI_API_BASE=https://api.example.test\n"
        "OPENAI_API_KEY=secret-value\n"
        "OPENAI_MODEL=test-model\n"
        "SQLITE_DB_PATH=:memory:\n"
        "VECTOR_STORE_PATH=./test_vector_store\n"
        "MAX_AGENT_STEPS=3\n"
        "MEMORY_EXTRACTOR_MODE=llm\n"
        "MEMORY_EXTRACTOR_TIMEOUT_SECONDS=4.5\n"
        "MEMORY_EXTRACTOR_MODEL=memory-model\n"
        "MEMORY_EXTRACTOR_MAX_INPUT_CHARS=1234\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("SQLITE_DB_PATH", raising=False)
    monkeypatch.delenv("VECTOR_STORE_PATH", raising=False)
    monkeypatch.delenv("MAX_AGENT_STEPS", raising=False)
    monkeypatch.delenv("MEMORY_EXTRACTOR_MODE", raising=False)
    monkeypatch.delenv("MEMORY_EXTRACTOR_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("MEMORY_EXTRACTOR_MODEL", raising=False)
    monkeypatch.delenv("MEMORY_EXTRACTOR_MAX_INPUT_CHARS", raising=False)

    load_dotenv(env_file)
    settings = get_settings()
    runtime = build_default_runtime(use_real_llm=True, settings=settings, enable_vector_store=False)

    assert settings.openai_api_base == "https://api.example.test"
    assert "secret-value" not in repr(settings)
    assert settings.vector_store_path == "./test_vector_store"
    assert settings.memory_extractor_mode == "llm"
    assert settings.memory_extractor_timeout_seconds == 4.5
    assert settings.memory_extractor_model == "memory-model"
    assert settings.memory_extractor_max_input_chars == 1234
    assert runtime.max_steps == 3
    assert isinstance(runtime.llm_client, OpenAICompatibleClient)
    assert runtime.llm_client.model == "test-model"


def test_start_api_function_exists():
    assert callable(start_api)
