"""HTTP API for the LEYRA cloud core."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, EmailStr

from .agents import build_agents
from .auth import hash_password, issue_token, require_role, verify_password
from .config import Settings, ensure_data_directory
from .orchestrator import Orchestrator
from .providers import ModelProvider
from .security import require_control_access
from .storage import Storage

router = APIRouter(prefix="/leyra/core", tags=["LEYRA Core"])


class TaskRequest(BaseModel):
    agent: str = Field(min_length=1, max_length=40)
    payload: dict[str, Any] = Field(default_factory=dict)


class MemoryRequest(BaseModel):
    namespace: str = Field(default="general", min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=20000)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    role: str = Field(pattern="^(viewer|operator|admin)$")


class ChatRequest(BaseModel):
    model: str = Field(min_length=1, max_length=160)
    messages: list[dict[str, Any]] = Field(min_length=1, max_length=100)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=32768)


def get_services(request: Request):
    return request.app.state.leyra_settings, request.app.state.leyra_storage, request.app.state.leyra_orchestrator


def protect(request: Request, minimum: str = "operator") -> dict:
    settings: Settings = request.app.state.leyra_settings
    return require_role(request, minimum, settings.control_token, settings.jwt_secret)


@router.post("/auth/login")
async def login(body: LoginRequest, request: Request):
    settings, storage, _ = get_services(request)
    user = storage.get_user(str(body.email))
    if not user or not user["active"] or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not settings.jwt_secret:
        raise HTTPException(status_code=503, detail="JWT signing secret is not configured")
    token = issue_token(user, settings.jwt_secret)
    storage.audit("auth.login", str(user["email"]), "completed")
    return {"access_token": token, "token_type": "bearer", "expires_in": 28800,
            "user": {"id": user["id"], "email": user["email"], "role": user["role"]}}


@router.post("/users", status_code=201)
async def create_user(body: UserCreateRequest, request: Request):
    protect(request, "admin")
    settings, storage, _ = get_services(request)
    if storage.get_user(str(body.email)):
        raise HTTPException(status_code=409, detail="User already exists")
    user_id = storage.create_user(str(body.email), hash_password(body.password), body.role)
    storage.audit("user.create", str(user_id), "completed")
    return {"id": user_id, "email": str(body.email).lower(), "role": body.role}


@router.get("/models")
async def list_models(request: Request):
    protect(request, "viewer")
    return await ModelProvider().models()


@router.post("/chat")
async def chat(body: ChatRequest, request: Request):
    claims = protect(request, "operator")
    payload = body.dict(exclude_none=True)
    result = await ModelProvider().chat(payload)
    storage = request.app.state.leyra_storage
    storage.audit("model.chat", str(claims.get("email", "unknown")), "completed")
    return result


@router.get("/health")
async def health(request: Request):
    settings, storage, _ = get_services(request)
    return {
        "service": "leyra-core",
        "status": "ready",
        "environment": settings.environment,
        "storage": storage.health(),
        "agents_registered": len(request.app.state.leyra_orchestrator.agents),
        "model_provider_configured": ModelProvider().configured(),
    }


@router.get("/agents")
async def agents(request: Request):
    protect(request, "viewer")
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
    protect(request, "admin")
    storage: Storage = request.app.state.leyra_storage
    return {"events": storage.list_audit(limit)}


def initialize_services(app) -> None:
    settings = Settings.from_env()
    ensure_data_directory(settings)
    storage = Storage(settings.database_path, settings.database_url, settings.redis_url)
    if settings.bootstrap_admin_email and settings.bootstrap_admin_password and not storage.get_user(settings.bootstrap_admin_email):
        if not settings.jwt_secret:
            raise RuntimeError("LEYRA_JWT_SECRET is required when bootstrapping an admin")
        storage.create_user(settings.bootstrap_admin_email, hash_password(settings.bootstrap_admin_password), "admin")
    app.state.leyra_settings = settings
    app.state.leyra_storage = storage
    app.state.leyra_orchestrator = Orchestrator(build_agents(storage), storage)
