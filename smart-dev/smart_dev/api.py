"""FastAPI HTTP API over the smart-dev tools, workflows, and agent.

Powers the "Dev" section of the frontend. Runs on a separate port (default 8030)
from the Quick Data API.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Iterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import prompts as P
from . import tools as T
from .agent.base import AgentError
from .agent.gemini_agent import GeminiAgent
from .utils import PathError

app = FastAPI(title="Smart Dev API", version="0.1.0")
agent = GeminiAgent()

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


def _handle(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except PathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# --------------------------------------------------------------------- models


class PathRequest(BaseModel):
    path: str
    max_files: int = 600


class DepsRequest(BaseModel):
    path: str
    audit: bool = True


class DeployRequest(BaseModel):
    path: str
    run_build: bool = False


class RollbackRequest(BaseModel):
    path: str
    target: str = "HEAD"
    confirm: bool = False


class WorkflowRequest(BaseModel):
    project_path: str = ""
    issue: str = ""
    target: str = ""


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


# ------------------------------------------------------------------ endpoints


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze")
def analyze(req: PathRequest) -> dict:
    return _handle(T.analyze_codebase, req.path, max_files=req.max_files)


@app.post("/api/tests")
def tests(req: PathRequest) -> dict:
    return _handle(T.run_tests, req.path)


@app.post("/api/dependencies")
def dependencies(req: DepsRequest) -> dict:
    return _handle(T.check_dependencies, req.path, audit=req.audit)


@app.post("/api/docs")
def docs(req: PathRequest) -> dict:
    return _handle(T.generate_docs, req.path)


@app.post("/api/deploy-preview")
def deploy_preview(req: DeployRequest) -> dict:
    return _handle(T.deploy_preview, req.path, run_build=req.run_build)


@app.post("/api/rollback")
def rollback(req: RollbackRequest) -> dict:
    return _handle(T.rollback_changes, req.path, target=req.target, confirm=req.confirm)


_WORKFLOWS = {
    "dev_setup": lambda r: P.dev_setup(r.project_path),
    "code_review": lambda r: P.code_review(r.project_path),
    "architecture_analysis": lambda r: P.architecture_analysis(r.project_path),
    "performance_audit": lambda r: P.performance_audit(r.project_path),
    "debug_investigation": lambda r: P.debug_investigation(r.issue, r.project_path),
    "refactor_planning": lambda r: P.refactor_planning(r.target, r.project_path),
}


@app.get("/api/workflows")
def list_workflows() -> dict:
    return {"workflows": list(_WORKFLOWS)}


@app.post("/api/workflow/{name}")
def run_workflow(name: str, req: WorkflowRequest) -> dict:
    fn = _WORKFLOWS.get(name)
    if fn is None:
        raise HTTPException(status_code=404, detail=f"Unknown workflow '{name}'.")
    return {"workflow": name, "markdown": _handle(fn, req)}


@app.get("/api/agent")
def agent_status() -> dict:
    return {"enabled": bool(agent._api_key), "model": agent.model, "backend": agent.name}


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


@app.post("/api/chat")
def chat(req: ChatRequest) -> StreamingResponse:
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty.")
    session_id = req.session_id or uuid.uuid4().hex

    def events() -> Iterator[str]:
        yield _sse({"type": "session", "session_id": session_id})
        try:
            for ev in agent.stream(session_id, req.message):
                yield _sse(ev.to_dict())
        except AgentError as exc:
            yield _sse({"type": "error", "message": str(exc)})
        except Exception as exc:
            yield _sse({"type": "error", "message": f"{type(exc).__name__}: {exc}"})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.delete("/api/chat/{session_id}")
def reset_chat(session_id: str) -> dict:
    agent.reset(session_id)
    return {"reset": session_id}


def main() -> None:
    import uvicorn

    port = int(os.environ.get("PORT", 8030))
    uvicorn.run("smart_dev.api:app", host="127.0.0.1", port=port, reload=True)


if __name__ == "__main__":
    main()
