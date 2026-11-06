"""LEYRA's provider-neutral OpenAI-compatible gateway.

This module deliberately talks only to an explicitly configured provider endpoint.
It does not automate browser sessions, solve challenges, scrape websites, or reuse
third-party session cookies.
"""
from __future__ import annotations

import hmac
import json
import os
from dataclasses import dataclass
from typing import AsyncIterator
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse


@dataclass(frozen=True)
class Settings:
    upstream_base_url: str
    upstream_api_key: str
    gateway_token: str
    timeout_seconds: float


def get_settings() -> Settings:
    """Load and validate secrets from environment variables."""
    base_url = os.getenv("LEYRA_UPSTREAM_BASE_URL", "").strip().rstrip("/")
    gateway_token = os.getenv("LEYRA_GATEWAY_TOKEN", "").strip()
    upstream_api_key = os.getenv("LEYRA_UPSTREAM_API_KEY", "").strip()

    if not base_url:
        raise HTTPException(status_code=503, detail="LEYRA provider is not configured.")
    if not gateway_token:
        raise HTTPException(status_code=503, detail="LEYRA gateway authentication is not configured.")

    parsed = urlsplit(base_url)
    local_hosts = {"localhost", "127.0.0.1", "::1"}
    is_local_http = parsed.scheme == "http" and parsed.hostname in local_hosts
    if parsed.scheme != "https" and not is_local_http:
        raise HTTPException(
            status_code=503,
            detail="Provider URL must use HTTPS (HTTP is allowed only for localhost).",
        )
    try:
        parsed.port
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="Provider URL port is invalid.") from exc
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise HTTPException(status_code=503, detail="Provider URL is invalid.")

    try:
        timeout_seconds = float(os.getenv("LEYRA_UPSTREAM_TIMEOUT_SECONDS", "90"))
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="Provider timeout must be numeric.") from exc
    if not 5 <= timeout_seconds <= 300:
        raise HTTPException(status_code=503, detail="Provider timeout must be between 5 and 300 seconds.")

    return Settings(
        upstream_base_url=base_url,
        upstream_api_key=upstream_api_key,
        gateway_token=gateway_token,
        timeout_seconds=timeout_seconds,
    )


def authorize(authorization: str | None, expected_token: str) -> None:
    """Require the LEYRA client token using a constant-time comparison."""
    scheme, _, supplied = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not supplied or not hmac.compare_digest(supplied, expected_token):
        raise HTTPException(status_code=401, detail="Invalid or missing LEYRA gateway token.")


def upstream_headers(settings: Settings) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if settings.upstream_api_key:
        headers["Authorization"] = f"Bearer {settings.upstream_api_key}"
    return headers


def upstream_url(settings: Settings, path: str) -> str:
    return f"{settings.upstream_base_url}/{path.lstrip('/')}"


app = FastAPI(
    title="LEYRA AI Gateway",
    version="0.1.0",
    description="Provider-neutral, OpenAI-compatible gateway for LEYRA IA.",
)
router = APIRouter(prefix="/leyra", tags=["LEYRA IA"])
MAX_REQUEST_BODY_BYTES = 2 * 1024 * 1024
MAX_MESSAGES_PER_REQUEST = 100


@router.get("/health")
async def health() -> JSONResponse:
    """Return non-sensitive readiness information."""
    configured = bool(
        os.getenv("LEYRA_UPSTREAM_BASE_URL", "").strip()
        and os.getenv("LEYRA_GATEWAY_TOKEN", "").strip()
    )
    return JSONResponse(
        {"service": "leyra-gateway", "status": "ready" if configured else "needs_configuration"}
    )


@router.get("/connection/test")
async def test_provider_connection(request: Request) -> JSONResponse:
    """Perform a real authenticated request to the configured provider's models endpoint."""
    settings = get_settings()
    authorize(request.headers.get("authorization"), settings.gateway_token)
    timeout = httpx.Timeout(settings.timeout_seconds, connect=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            upstream = await client.get(
                upstream_url(settings, "models"),
                headers=upstream_headers(settings),
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="The model provider timed out.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not reach the configured model provider.") from exc

    if upstream.is_error:
        # Do not relay provider bodies: they can contain account or infrastructure details.
        raise HTTPException(
            status_code=502,
            detail=f"Provider connection failed with HTTP {upstream.status_code}. Check the provider URL and credential.",
        )
    return JSONResponse({
        "service": "leyra-gateway",
        "connection": "connected",
        "provider_host": urlsplit(settings.upstream_base_url).hostname,
        "models_endpoint_status": upstream.status_code,
        "api_key_configured": bool(settings.upstream_api_key),
    })


@router.get("/v1/models")
async def list_models(request: Request) -> Response:
    settings = get_settings()
    authorize(request.headers.get("authorization"), settings.gateway_token)
    timeout = httpx.Timeout(settings.timeout_seconds, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            upstream = await client.get(
                upstream_url(settings, "models"),
                headers=upstream_headers(settings),
            )
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Could not reach the configured model provider.") from exc

    if upstream.is_error:
        raise HTTPException(status_code=502, detail="The configured provider rejected the models request.")
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/json"),
    )


@router.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Response:
    settings = get_settings()
    authorize(request.headers.get("authorization"), settings.gateway_token)

    # Read incrementally so oversized/chunked requests are rejected before
    # buffering the entire body in memory.
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_REQUEST_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Request body exceeds the 2 MiB limit.")
        body.extend(chunk)
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON.") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object.")
    if not isinstance(payload.get("model"), str) or not payload["model"].strip():
        raise HTTPException(status_code=400, detail="A model name is required.")
    if not isinstance(payload.get("messages"), list) or not payload["messages"]:
        raise HTTPException(status_code=400, detail="At least one message is required.")
    if len(payload["messages"]) > MAX_MESSAGES_PER_REQUEST:
        raise HTTPException(status_code=413, detail="A maximum of 100 messages is allowed per request.")

    timeout = httpx.Timeout(settings.timeout_seconds, connect=10.0)
    client = httpx.AsyncClient(timeout=timeout)
    headers = upstream_headers(settings)
    headers["Content-Type"] = "application/json"
    url = upstream_url(settings, "chat/completions")

    streaming_handed_off = False
    try:
        if payload.get("stream") is True:
            outgoing = client.build_request("POST", url, headers=headers, json=payload)
            upstream = await client.send(outgoing, stream=True)
            if upstream.is_error:
                await upstream.aclose()
                await client.aclose()
                raise HTTPException(
                    status_code=502,
                    detail="The configured provider rejected the chat request.",
                )

            async def stream_body() -> AsyncIterator[bytes]:
                try:
                    async for chunk in upstream.aiter_raw():
                        yield chunk
                finally:
                    await upstream.aclose()
                    await client.aclose()

            streaming_handed_off = True
            return StreamingResponse(
                stream_body(),
                status_code=upstream.status_code,
                media_type=upstream.headers.get("content-type", "text/event-stream"),
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        upstream = await client.post(url, headers=headers, json=payload)
        if upstream.is_error:
            raise HTTPException(
                status_code=502,
                detail="The configured provider rejected the chat request.",
            )
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type", "application/json"),
        )
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="The model provider timed out.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not reach the configured model provider.") from exc
    finally:
        if not streaming_handed_off:
            await client.aclose()


# Standalone development app; the main LMArenaBridge app mounts the same router.
app.include_router(router)
