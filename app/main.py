from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.contracts import AuthRequest, AuthResponse, UserPublic
from app.llm.fake import ScriptedLLM
from app.llm.openai_client import OpenAICompatibleClient
from app.memory.extractor import HeuristicMemoryExtractor, LLMMemoryExtractor
from app.memory.manager import MemoryManager
from app.memory.vector_store import ChromaVectorMemoryStore, NullVectorMemoryStore
from app.runtime.action_parser import ActionParser
from app.runtime.auth_manager import AuthManager, AuthValidationError, DuplicateUsernameError
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.context_summarizer import LLMContextSummarizer, RuleBasedContextSummarizer
from app.runtime.async_manager import AsyncManager
from app.runtime.session_manager import SessionManager
from app.runtime.trace_logger import TraceLogger
from app.storage.sqlite_store import SQLiteStore
from app.tools.calculator import CalculatorTool
from app.tools.long_search import LongSearchTool
from app.tools.registry import ToolRegistry
from app.tools.search import SearchTool
from app.tools.todo import TodoTool
from app.tools.weather import WeatherTool


class SendMessageRequest(BaseModel):
    content: str


class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"


app = FastAPI(
    title="Multi-Session Personal Productivity Agent",
    default_response_class=UTF8JSONResponse,
)


def build_default_runtime(
    scripted_responses: list[dict[str, object]] | None = None,
    use_real_llm: bool = False,
    settings: Settings | None = None,
    enable_vector_store: bool | None = None,
) -> AgentRuntime:
    settings = settings or get_settings()
    db_path = settings.sqlite_db_path if use_real_llm else ":memory:"
    store = SQLiteStore(db_path)
    store.init_schema()
    session_manager = SessionManager(store)
    trace_logger = TraceLogger(store)
    async_manager = AsyncManager(store, session_manager, trace_logger)
    use_vector_store = use_real_llm if enable_vector_store is None else enable_vector_store
    llm_client = OpenAICompatibleClient(settings) if use_real_llm else ScriptedLLM(scripted_responses or [])
    memory_manager = MemoryManager(
        store,
        vector_store=_build_vector_store(settings) if use_vector_store else NullVectorMemoryStore(),
        extractor=_build_memory_extractor(settings, use_real_llm, llm_client),
    )
    context_summarizer = _build_context_summarizer(settings, use_real_llm, llm_client)
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(WeatherTool())
    registry.register(SearchTool())
    registry.register(TodoTool(session_manager))
    registry.register(LongSearchTool(async_manager))
    runtime = AgentRuntime(
        session_manager=session_manager,
        llm_client=llm_client,
        action_parser=ActionParser(),
        tool_registry=registry,
        trace_logger=trace_logger,
        max_steps=settings.max_agent_steps,
        memory_manager=memory_manager,
        context_summarizer=context_summarizer,
    )
    runtime.auth_manager = AuthManager(store)
    return runtime


def _build_memory_extractor(settings: Settings, use_real_llm: bool, llm_client):
    if not use_real_llm or settings.memory_extractor_mode.lower() != "llm":
        return HeuristicMemoryExtractor()
    try:
        return LLMMemoryExtractor(
            json_client=llm_client,
            fallback=HeuristicMemoryExtractor(),
            model=settings.memory_extractor_model or settings.openai_model,
            timeout_seconds=settings.memory_extractor_timeout_seconds,
            max_input_chars=settings.memory_extractor_max_input_chars,
        )
    except Exception:
        return HeuristicMemoryExtractor()


def _build_context_summarizer(settings: Settings, use_real_llm: bool, llm_client):
    fallback = RuleBasedContextSummarizer()
    if not use_real_llm or settings.context_summarizer_mode.lower() != "llm":
        return fallback
    try:
        return LLMContextSummarizer(
            json_client=llm_client,
            fallback=fallback,
            model=settings.context_summarizer_model or settings.openai_model,
            timeout_seconds=settings.context_summarizer_timeout_seconds,
            max_input_chars=settings.context_summarizer_max_input_chars,
            max_summary_chars=settings.context_summarizer_max_summary_chars,
        )
    except Exception:
        return fallback


def _build_vector_store(settings: Settings):
    try:
        return ChromaVectorMemoryStore(settings.vector_store_path)
    except Exception:
        return NullVectorMemoryStore()


def _ensure_runtime() -> AgentRuntime:
    runtime = getattr(app.state, "runtime", None)
    if runtime is None:
        runtime = build_default_runtime()
        app.state.runtime = runtime
        app.state.session_manager = runtime.session_manager
        app.state.trace_logger = runtime.trace_logger
        app.state.auth_manager = runtime.auth_manager
    app.state.session_manager = runtime.session_manager
    app.state.trace_logger = runtime.trace_logger
    app.state.auth_manager = runtime.auth_manager
    return runtime


def _get_auth_manager() -> AuthManager:
    _ensure_runtime()
    return app.state.auth_manager


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return token


def get_current_user(authorization: str | None = Header(default=None)) -> UserPublic:
    token = _extract_bearer_token(authorization)
    user = _get_auth_manager().get_user_for_token(token)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")
    return user


def _ensure_owned_session(runtime: AgentRuntime, user_id: str, session_id: str) -> None:
    if not runtime.session_manager.session_exists(user_id, session_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(request: AuthRequest) -> AuthResponse:
    auth_manager = _get_auth_manager()
    try:
        user = auth_manager.register_user(request.username, request.password)
    except DuplicateUsernameError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    except AuthValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    token = auth_manager.issue_token(user.user_id)
    return AuthResponse(token=token, user=user)


@app.post("/auth/login")
def login(request: AuthRequest) -> AuthResponse:
    auth_manager = _get_auth_manager()
    user = auth_manager.authenticate_user(request.username, request.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    token = auth_manager.issue_token(user.user_id)
    return AuthResponse(token=token, user=user)


@app.get("/auth/me")
def me(current_user: UserPublic = Depends(get_current_user)) -> dict[str, object]:
    return {"user": current_user.model_dump(mode="json")}


@app.post("/auth/logout")
def logout(
    authorization: str | None = Header(default=None),
    current_user: UserPublic = Depends(get_current_user),
) -> dict[str, str]:
    token = _extract_bearer_token(authorization)
    _get_auth_manager().revoke_token(token)
    return {"status": "ok"}


@app.get("/sessions")
def list_sessions(current_user: UserPublic = Depends(get_current_user)) -> dict[str, object]:
    runtime = _ensure_runtime()
    sessions = runtime.session_manager.list_sessions(current_user.user_id)
    return {"sessions": [session.model_dump(mode="json") for session in sessions]}


@app.post("/sessions", status_code=status.HTTP_201_CREATED)
def create_session(current_user: UserPublic = Depends(get_current_user)) -> dict[str, object]:
    runtime = _ensure_runtime()
    session = runtime.session_manager.create_session(current_user.user_id)
    return {"session": session.model_dump(mode="json")}


@app.get("/sessions/{session_id}/messages")
def list_messages(session_id: str, current_user: UserPublic = Depends(get_current_user)) -> dict[str, object]:
    runtime = _ensure_runtime()
    _ensure_owned_session(runtime, current_user.user_id, session_id)
    messages = runtime.session_manager.list_messages(current_user.user_id, session_id)
    return {"messages": [message.model_dump(mode="json") for message in messages]}


@app.post("/sessions/{session_id}/messages")
def send_message(
    session_id: str,
    request: SendMessageRequest,
    current_user: UserPublic = Depends(get_current_user),
) -> dict[str, str]:
    runtime = _ensure_runtime()
    _ensure_owned_session(runtime, current_user.user_id, session_id)
    result = runtime.handle_user_message(current_user.user_id, session_id, request.content)
    return {"answer": result.answer, "session_status": result.session_status.value}


@app.get("/sessions/{session_id}/todos")
def list_todos(session_id: str, current_user: UserPublic = Depends(get_current_user)) -> dict[str, object]:
    runtime = _ensure_runtime()
    _ensure_owned_session(runtime, current_user.user_id, session_id)
    todos = runtime.session_manager.list_todos(current_user.user_id, session_id)
    return {"todos": [todo.model_dump(mode="json") for todo in todos]}


@app.get("/sessions/{session_id}/trace")
def list_trace(session_id: str, current_user: UserPublic = Depends(get_current_user)) -> dict[str, object]:
    runtime = _ensure_runtime()
    _ensure_owned_session(runtime, current_user.user_id, session_id)
    if runtime.trace_logger is None:
        raise HTTPException(status_code=500, detail="trace logger is not configured")
    traces = runtime.trace_logger.list_traces(current_user.user_id, session_id)
    return {"traces": [trace.model_dump(mode="json") for trace in traces]}


def start_api(host: str = "127.0.0.1", port: int = 8000, use_real_llm: bool = True) -> None:
    import uvicorn

    app.state.runtime = build_default_runtime(use_real_llm=use_real_llm)
    app.state.session_manager = app.state.runtime.session_manager
    app.state.trace_logger = app.state.runtime.trace_logger
    app.state.auth_manager = app.state.runtime.auth_manager
    uvicorn.run(app, host=host, port=port)


def main() -> None:
    print("Multi-Session Personal Productivity Agent")
    print("Run API server with: python start_server.py")
    print("Or use: uvicorn app.main:app --reload")


if __name__ == "__main__":
    main()
