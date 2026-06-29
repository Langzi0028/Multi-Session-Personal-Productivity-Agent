from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_submission_documents_exist_and_mention_real_commands():
    files = [
        ROOT / "README.md",
        ROOT / "docs" / "ai_prompt_and_problem_solving.md",
        ROOT / "docs" / "demo_questions_expected.md",
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

    prompt_doc = (ROOT / "docs" / "ai_prompt_and_problem_solving.md").read_text(encoding="utf-8")
    assert "Runtime" in prompt_doc
    assert "Prompt" in prompt_doc
    assert "问题解决" in prompt_doc

    demo_questions = (ROOT / "docs" / "demo_questions_expected.md").read_text(encoding="utf-8")
    assert "提问" in demo_questions
    assert "应该回答" in demo_questions
