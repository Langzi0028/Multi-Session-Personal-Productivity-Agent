from __future__ import annotations

from pathlib import Path


FORBIDDEN_RUNTIME_TOKENS = (
    "langgraph",
    "langchain",
    "AIMessage",
    "ChatOpenAI",
    "StateGraph",
)


def test_app_code_does_not_depend_on_langgraph_or_langchain():
    project_root = Path(__file__).resolve().parents[1]

    for path in (project_root / "app").rglob("*.py"):
        relative_path = path.relative_to(project_root)
        content = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_RUNTIME_TOKENS:
            assert token not in content, f"{relative_path} still references {token}"
