from pathlib import Path


FRONTEND = Path(__file__).resolve().parents[1] / "front-end"


def test_frontend_document_title_matches_integrated_agent_product():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")

    assert "<title>Multi-Session Agent</title>" in html
    assert "vibe-coding" not in html


def test_root_readme_documents_frontend_integration_startup():
    readme = (FRONTEND.parent / "README.md").read_text(encoding="utf-8")

    assert "front-end" in readme
    assert "npm run dev" in readme
    assert "start_manual_demo.py" in readme
