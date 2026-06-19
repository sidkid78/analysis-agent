"""FastAPI HTTP API over the shared fleet.

Mirrors the MCP tools as REST endpoints so the Next.js frontend can drive the
same fleet the MCP server uses.
"""

from __future__ import annotations

import json
import uuid
from typing import Iterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import prompts
from .agent.base import AgentError
from .agent.gemini_agent import GeminiAgent
from .fleet import backup, deployment, logs, monitoring, scaling, secrets
from .fleet.model import FleetError, default_fleet

app = FastAPI(title="Infrastructure Automation API", version="0.3.0")
fleet = default_fleet
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
    except FleetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# --------------------------------------------------------------------- models


class DeployRequest(BaseModel):
    app_name: str
    environment: str = "staging"
    strategy: str = "rolling"
    confirm: bool = False


class ScaleRequest(BaseModel):
    resource_type: str
    target_capacity: int
    confirm: bool = False


class BackupRequest(BaseModel):
    data_source: str
    backup_type: str = "incremental"
    retention_days: int = 30
    confirm: bool = False


class RotateRequest(BaseModel):
    secret_type: str = "all"
    environment: str = "all"
    force: bool = False
    confirm: bool = False


class LogsRequest(BaseModel):
    log_source: str = "all"
    time_range: str = "1h"
    log_level: str = "ERROR"
    pattern: str = ""


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


# ------------------------------------------------------------------ endpoints


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/fleet")
def fleet_status() -> dict:
    return fleet.snapshot()


@app.post("/api/fleet/reset")
def reset_fleet() -> dict:
    fleet.reset()
    return {"reset": True, "services": len(fleet.services)}


@app.get("/api/monitor")
def monitor(service_filter: str = "all", metrics: str = "standard", alert_threshold: float = 80.0) -> dict:
    return _handle(monitoring.monitor_services, fleet, service_filter, metrics, alert_threshold)


@app.post("/api/deploy")
def deploy(req: DeployRequest) -> dict:
    return _handle(
        deployment.deploy_application, fleet, req.app_name, req.environment, req.strategy, req.confirm
    )


@app.post("/api/scale")
def scale(req: ScaleRequest) -> dict:
    return _handle(scaling.scale_resources, fleet, req.resource_type, req.target_capacity, req.confirm)


@app.post("/api/backup")
def do_backup(req: BackupRequest) -> dict:
    return _handle(
        backup.backup_data, fleet, req.data_source, req.backup_type, req.retention_days, req.confirm
    )


@app.post("/api/secrets/rotate")
def rotate(req: RotateRequest) -> dict:
    return _handle(
        secrets.rotate_secrets, fleet, req.secret_type, req.environment, req.force, req.confirm
    )


@app.post("/api/logs")
def analyze(req: LogsRequest) -> dict:
    return _handle(
        logs.analyze_logs, fleet, req.log_source, req.time_range, req.log_level, req.pattern
    )


@app.get("/api/workflows/{name}")
def run_workflow(name: str, arg: str = "", arg2: str = "") -> dict:
    """Run an agentic prompt and return its Markdown. `arg`/`arg2` are the
    workflow's positional parameters (e.g. application + target_env)."""
    runners = {
        "infra-health-check": lambda: prompts.infra_health_check_prompt(fleet, arg or "all"),
        "deployment-strategy": lambda: prompts.deployment_strategy_prompt(
            fleet, arg, arg2 or "production"
        ),
        "scaling-analysis": lambda: prompts.scaling_analysis_prompt(
            fleet, arg or "compute", arg2 or "auto"
        ),
        "incident-response": lambda: prompts.incident_response_prompt(fleet, arg, arg2 or "medium"),
        "security-audit": lambda: prompts.security_audit_prompt(fleet, arg or "full", arg2),
        "disaster-recovery": lambda: prompts.disaster_recovery_prompt(fleet, arg, arg2 or "4h"),
    }
    if name not in runners:
        raise HTTPException(status_code=404, detail=f"Unknown workflow '{name}'.")
    return {"workflow": name, "markdown": _handle(runners[name])}


@app.get("/api/agent")
def agent_status() -> dict:
    """Whether the chat agent is configured (API key present) and its model."""
    return {"enabled": bool(agent._api_key), "model": agent.model, "backend": agent.name}


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


@app.post("/api/chat")
def chat(req: ChatRequest) -> StreamingResponse:
    """Stream the agent's work as Server-Sent Events. Session state lives on the
    server (keyed by session_id); the client only sends the new message."""
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

    port = int(os.environ.get("PORT", 8040))
    uvicorn.run("infra_automation.api:app", host="127.0.0.1", port=port, reload=True)


if __name__ == "__main__":
    main()
