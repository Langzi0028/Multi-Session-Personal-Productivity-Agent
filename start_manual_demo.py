from __future__ import annotations

import uvicorn

from app.demo_runtime import build_manual_demo_runtime
from app.main import app


def start_manual_demo(host: str = "127.0.0.1", port: int = 8000) -> None:
    app.state.runtime = build_manual_demo_runtime()
    app.state.session_manager = app.state.runtime.session_manager
    app.state.trace_logger = app.state.runtime.trace_logger
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_manual_demo()
