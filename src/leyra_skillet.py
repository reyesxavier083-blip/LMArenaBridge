"""Read-only Skillet hosted MCP client for LEYRA."""
from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlsplit

import httpx

DEFAULT_TIMEOUT = 20.0
ALLOWED_HOST = "registry.skillet.md"


class SkilletError(RuntimeError):
    """A safe, user-facing Skillet connection error."""


def _endpoint() -> str:
    endpoint = os.getenv("LEYRA_SKILLET_MCP_URL", "").strip()
    if not endpoint:
        raise SkilletError("Skillet MCP is not configured.")
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "https"
        or parsed.hostname != ALLOWED_HOST
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/api/v1/mcp/")
        or len(parsed.path) > 512
    ):
        raise SkilletError("Skillet MCP URL is invalid.")
    return endpoint


def _decode_response(response: httpx.Response) -> dict[str, Any]:
    if response.status_code == 202 or not response.content:
        return {}
    if response.is_error:
        if response.status_code in (401, 403):
            raise SkilletError("Skillet MCP token is invalid, revoked, or lacks read access.")
        if response.status_code == 429:
            raise SkilletError("Skillet MCP rate limit reached; retry later.")
        raise SkilletError(f"Skillet MCP request failed with HTTP {response.status_code}.")
    raw = response.text.strip()
    if raw.startswith("event:") or "\ndata:" in raw:
        data = [line[5:].strip() for line in raw.splitlines() if line.startswith("data:")]
        raw = data[-1] if data else ""
    try:
        value = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise SkilletError("Skillet MCP returned an invalid JSON-RPC response.") from exc
    if not isinstance(value, dict):
        raise SkilletError("Skillet MCP returned an unexpected response.")
    if isinstance(value.get("error"), dict):
        message = value["error"].get("message", "MCP tool error")
        raise SkilletError(str(message)[:300])
    return value


async def _rpc(
    client: httpx.AsyncClient,
    endpoint: str,
    method: str,
    params: dict[str, Any] | None = None,
    request_id: int | None = 1,
    session_id: str | None = None,
) -> tuple[dict[str, Any], str | None]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if method != "initialize":
        headers["MCP-Protocol-Version"] = "2025-06-18"
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    body: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if request_id is not None:
        body["id"] = request_id
    if params is not None:
        body["params"] = params
    try:
        response = await client.post(endpoint, headers=headers, json=body)
    except httpx.TimeoutException as exc:
        raise SkilletError("Skillet MCP timed out.") from exc
    except httpx.HTTPError as exc:
        raise SkilletError("Could not reach Skillet MCP.") from exc
    current_session = response.headers.get("Mcp-Session-Id") or session_id
    return _decode_response(response), current_session


async def call_skillet_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Initialize the hosted MCP connection and call one read-only kit tool."""
    if name not in {"list_skills", "search_skills", "get_skill"}:
        raise SkilletError("Unsupported Skillet MCP tool.")
    endpoint = _endpoint()
    timeout = httpx.Timeout(DEFAULT_TIMEOUT, connect=8.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        init, session = await _rpc(
            client,
            endpoint,
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "LEYRA IA", "version": "0.1.0"},
            },
            request_id=1,
        )
        if not isinstance(init.get("result"), dict):
            raise SkilletError("Skillet MCP initialization failed.")
        await _rpc(client, endpoint, "notifications/initialized", request_id=None, session_id=session)
        listed, session = await _rpc(client, endpoint, "tools/list", request_id=2, session_id=session)
        tool_rows = listed.get("result", {}).get("tools", [])
        available = {
            item.get("name") for item in tool_rows
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        remote_name = name
        if name == "search_skills" and name not in available and "search" in available:
            remote_name = "search"
        if remote_name not in available:
            raise SkilletError("The connected Skillet server does not expose the requested read-only tool.")
        params = {"name": remote_name, "arguments": arguments or {}}
        response, _ = await _rpc(client, endpoint, "tools/call", params, request_id=3, session_id=session)
        result = response.get("result")
        if not isinstance(result, dict):
            raise SkilletError("Skillet MCP returned no tool result.")
        if result.get("isError"):
            raise SkilletError("Skillet MCP tool reported an error.")
        return result


async def skillet_tool_text(name: str, raw_arguments: str) -> str:
    """Validate model arguments and return bounded JSON text for the model."""
    try:
        arguments = json.loads(raw_arguments or "{}")
    except json.JSONDecodeError:
        return json.dumps({"error": "Tool arguments must be valid JSON."})
    if not isinstance(arguments, dict):
        return json.dumps({"error": "Tool arguments must be an object."})
    if name == "search_skills":
        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip() or len(query) > 200:
            return json.dumps({"error": "A search query of 1–200 characters is required."})
        arguments = {"query": query.strip()}
    elif name == "get_skill":
        slug = arguments.get("slug")
        if not isinstance(slug, str) or not slug.strip() or len(slug) > 200:
            return json.dumps({"error": "A skill slug of 1–200 characters is required."})
        arguments = {"slug": slug.strip()}
    elif name == "list_skills":
        arguments = {}
    try:
        result = await call_skillet_tool(name, arguments)
        content = result.get("content", [])
        text_items = [
            item.get("text", "") for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        return json.dumps({"tool": name, "content": text_items}, ensure_ascii=False)
    except SkilletError as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
