from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_submission_documents_exist_and_mention_real_commands():
    files = [
        ROOT / "README.md",
        ROOT / "docs" / "design.md",
        ROOT / "docs" / "prompts.md",
        ROOT / "docs" / "problem_solving_log.md",
        ROOT / "docs" / "demo_script.md",
    ]
    for file in files:
        assert file.exists()
        assert file.read_text(encoding="utf-8").strip()

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "python -m pytest tests/ -q" in readme
    assert "uvicorn app.main:app --reload" in readme
    assert "Chroma" in readme
    assert "VECTOR_STORE_PATH" in readme
    assert "LLMMemoryExtractor" in readme
    assert "MEMORY_EXTRACTOR_MODE" in readme

    assert "/auth/register" in readme
    assert "Authorization: Bearer" in readme
    assert "GET /sessions" in readme

    demo = (ROOT / "docs" / "demo_script.md").read_text(encoding="utf-8")
    assert "/auth/register" in demo
    assert "Authorization: Bearer" in demo
    assert "GET /sessions" in demo
