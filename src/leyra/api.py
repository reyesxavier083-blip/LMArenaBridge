"""HTTP API for the LEYRA cloud core."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .agents import build_agents
from .config import Settings, ensure_data_directory
from .orchestrator import Orchestrator
from .security import require_control_access
from .storage import Storage

router = APIRouter(prefix="/leyra/core", tags=["LEYRA Core"])


class TaskRequest(BaseModel):
    agent: str = Field(min_length=1, max_length=40)
    payload: dict[str, Any] = Field(default_factory=dict)


class MemoryRequest(BaseModel):
    namespace: str = Field(default="general", min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=20000)


def get_services(request: Request):
    return request.app.state.leyra_settings, request.app.state.leyra_storage, request.app.state.leyra_orchestrator


def protect(request: Request) -> None:
    settings: Settings = request.app.state.leyra_settings
    require_control_access(request, settings.control_token)


@router.get("/health")
async def health(request: Request):
    settings, storage, _ = get_services(request)
    return {
        "service": "leyra-core",
        "status": "ready",
        "environment": settings.environment,
        "storage": "sqlite",
        "agents_registered": len(request.app.state.leyra_orchestrator.agents),
    }


@router.get("/agents")
async def agents(request: Request):
    protect(request)
    orchestrator: Orchestrator = request.app.state.leyra_orchestrator
    return {"agents": sorted(orchestrator.agents.keys())}


@router.post("/tasks")
async def dispatch_task(body: TaskRequest, request: Request):
    protect(request)
    orchestrator: Orchestrator = request.app.state.leyra_orchestrator
    result = await orchestrator.dispatch(body.agent, body.payload)
    if result.status == "rejected":
        raise HTTPException(status_code=400, detail=result.message)
    return {
        "agent": result.agent,
        "status": result.status,
        "message": result.message,
        "data": result.data,
    }


@router.post("/memory")
async def save_memory(body: MemoryRequest, request: Request):
    protect(request)
    storage: Storage = request.app.state.leyra_storage
    memory_id = storage.save_memory(body.namespace, body.content)
    storage.audit("memory.write", "api", "completed")
    return {"status": "saved", "memory_id": memory_id}


@router.get("/memory")
async def read_memory(request: Request, namespace: str = "general", limit: int = 50):
    protect(request)
    storage: Storage = request.app.state.leyra_storage
    return {"items": storage.list_memory(namespace, limit)}


@router.get("/audit")
async def read_audit(request: Request, limit: int = 50):
    protect(request)
    storage: Storage = request.app.state.leyra_storage
    return {"events": storage.list_audit(limit)}


def initialize_services(app) -> None:
    settings = Settings.from_env()
    ensure_data_directory(settings)
    storage = Storage(settings.database_path)
    app.state.leyra_settings = settings
    app.state.leyra_storage = storage
    app.state.leyra_orchestrator = Orchestrator(build_agents(storage), storage)
