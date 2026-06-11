"""FastAPI HTTP API over the shared analysis engine.

Mirrors the MCP tools as REST endpoints so the Next.js frontend can drive the
same engine the MCP server uses.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Iterator

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from .agent.base import AgentError
from .agent.gemini_agent import GeminiAgent
from .config import DATA_DIR
from .engine import analysis, charts, pdf, playbooks, quality, query, report
from .engine.store import DatasetError, default_store

app = FastAPI(title="Quick Data API", version="0.1.0")
store = default_store
agent = GeminiAgent()

app.add_middleware(
    CORSMiddleware,
    # Allow any localhost port — the Next dev server hops ports when one is taken.
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


def _handle(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except DatasetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# --------------------------------------------------------------------- models


class LoadSampleRequest(BaseModel):
    filename: str
    dataset_name: str | None = None


class ChartRequest(BaseModel):
    chart_type: str
    x: str | None = None
    y: str | None = None
    bins: int = 10


class QueryRequest(BaseModel):
    filters: list[str] = []
    group_by: list[str] = []
    metrics: list[str] = []
    sort_by: str | None = None
    descending: bool = True
    limit: int = 50


class CleanRequest(BaseModel):
    operations: list[str]


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


# ------------------------------------------------------------------ endpoints


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/samples")
def list_samples() -> dict[str, list[str]]:
    """Bundled sample datasets the frontend can offer as one-click loads."""
    if not DATA_DIR.exists():
        return {"samples": []}
    names = [
        p.name
        for ext in ("*.json", "*.csv", "*.tsv")
        for p in sorted(DATA_DIR.glob(ext))
    ]
    return {"samples": names}


@app.post("/api/datasets/load-sample")
def load_sample(req: LoadSampleRequest) -> dict:
    path = (DATA_DIR / req.filename).resolve()
    if DATA_DIR.resolve() not in path.parents or not path.exists():
        raise HTTPException(status_code=404, detail=f"Unknown sample '{req.filename}'.")
    name = req.dataset_name or path.stem
    info = _handle(store.load_file, name, path)
    return info.to_dict()


@app.post("/api/datasets/upload")
async def upload(file: UploadFile = File(...), dataset_name: str | None = None) -> dict:
    raw = await file.read()
    name = dataset_name or Path(file.filename or "dataset").stem
    info = _handle(store.load_bytes, name, raw, file.filename or "upload.csv")
    return info.to_dict()


@app.get("/api/datasets")
def list_datasets() -> dict:
    return {"datasets": [i.to_dict() for i in store.list_info()]}


@app.delete("/api/datasets/{name}")
def delete_dataset(name: str) -> dict:
    store.remove(name)
    return {"removed": name}


@app.get("/api/datasets/{name}/breakdown")
def breakdown(name: str) -> dict:
    return _handle(analysis.breakdown, store, name)


@app.get("/api/datasets/{name}/suggestions")
def suggestions(name: str) -> dict:
    return _handle(analysis.suggest_analysis, store, name)


@app.get("/api/datasets/{name}/segment")
def segment(name: str, column: str) -> dict:
    return _handle(analysis.segment_by_column, store, name, column)


@app.get("/api/datasets/{name}/correlations")
def correlations(name: str, threshold: float = 0.5) -> dict:
    return _handle(analysis.find_correlations, store, name, threshold)


@app.post("/api/datasets/{name}/chart")
def chart(name: str, req: ChartRequest) -> dict:
    return _handle(
        charts.build_chart, store, name, req.chart_type, x=req.x, y=req.y, bins=req.bins
    )


@app.post("/api/datasets/{name}/query")
def query_dataset(name: str, req: QueryRequest) -> dict:
    return _handle(
        query.run_query,
        store,
        name,
        req.filters,
        req.group_by,
        req.metrics,
        req.sort_by,
        req.descending,
        req.limit,
    )


@app.get("/api/datasets/{name}/profile")
def profile_dataset(name: str) -> dict:
    return _handle(quality.profile, store, name)


@app.post("/api/datasets/{name}/clean")
def clean_dataset(name: str, req: CleanRequest) -> dict:
    return _handle(quality.clean, store, name, req.operations)


@app.get("/api/datasets/{name}/playbook/{playbook}")
def run_playbook(name: str, playbook: str) -> dict:
    return _handle(playbooks.run, store, playbook, name)


@app.get("/api/datasets/{name}/report")
def dataset_report(name: str) -> dict:
    return _handle(report.generate_report, store, name)


@app.get("/api/datasets/{name}/report.pdf")
def dataset_report_pdf(name: str) -> Response:
    rep = _handle(report.generate_report, store, name)
    data = pdf.report_to_pdf(rep)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}-report.pdf"'},
    )


@app.get("/api/agent")
def agent_status() -> dict:
    """Whether the chat agent is configured (API key present) and its model."""
    enabled = bool(agent._api_key)  # noqa: SLF001 - simple readiness check
    return {"enabled": enabled, "model": agent.model, "backend": agent.name}


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


@app.post("/api/chat")
def chat(req: ChatRequest) -> StreamingResponse:
    """Stream the agent's work as Server-Sent Events.

    Session state lives on the server (keyed by session_id), so the client only
    sends the new message; full tool context is retained across turns.
    """
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
        except Exception as exc:  # don't leave the stream hanging on a crash
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
    """Console entry point: run the dev server."""
    import os
    import uvicorn

    port = int(os.environ.get("PORT", 8020))
    uvicorn.run("quickdata.api:app", host="127.0.0.1", port=port, reload=True)


if __name__ == "__main__":
    main()
