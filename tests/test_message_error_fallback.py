from fastapi.testclient import TestClient

from api_auth_helpers import create_authenticated_session
from app.contracts import ErrorCode, SessionStatus
from app.llm.base import LLMClient
from app.main import app, build_default_runtime
from app.runtime.action_parser import ActionParserError


class FailingLLM:
    def complete(self, context: list[dict[str, object]]) -> dict[str, object]:
        raise ActionParserError(ErrorCode.LLM_API_ERROR, "simulated upstream failure")


class InvalidOutputLLM:
    def complete(self, context: list[dict[str, object]]) -> dict[str, object]:
        return {"type": "unexpected"}


def install_runtime(llm_client: LLMClient) -> TestClient:
    runtime = build_default_runtime()
    runtime.llm_client = llm_client
    app.state.runtime = runtime
    app.state.session_manager = runtime.session_manager
    app.state.trace_logger = runtime.trace_logger
    app.state.auth_manager = runtime.auth_manager
    return TestClient(app)


def test_message_endpoint_returns_fallback_instead_of_500_when_llm_fails():
    client = install_runtime(FailingLLM())
    headers, session_id = create_authenticated_session(client)

    response = client.post(
        f"/sessions/{session_id}/messages",
        headers=headers,
        json={"content": "你好"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_status"] == SessionStatus.ERROR.value
    assert "暂时无法完成" in body["answer"]
    traces = client.get(f"/sessions/{session_id}/trace", headers=headers).json()["traces"]
    assert traces[-1]["status"] == "error"
    assert traces[-1]["error"] == ErrorCode.LLM_API_ERROR.value


def test_message_endpoint_returns_fallback_instead_of_500_for_invalid_llm_output():
    client = install_runtime(InvalidOutputLLM())
    headers, session_id = create_authenticated_session(client)

    response = client.post(
        f"/sessions/{session_id}/messages",
        headers=headers,
        json={"content": "你好"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_status"] == SessionStatus.ERROR.value
    traces = client.get(f"/sessions/{session_id}/trace", headers=headers).json()["traces"]
    assert traces[-1]["error"] == ErrorCode.INVALID_LLM_OUTPUT.value
