import json

import httpx
import pytest

from src import leyra_skillet


def test_endpoint_requires_private_configuration(monkeypatch):
    monkeypatch.delenv("LEYRA_SKILLET_MCP_URL", raising=False)
    with pytest.raises(leyra_skillet.SkilletError, match="not configured"):
        leyra_skillet._endpoint()


@pytest.mark.parametrize(
    "url",
    [
        "http://registry.skillet.md/api/v1/mcp/token",
        "https://example.com/api/v1/mcp/token",
        "https://registry.skillet.md.evil.test/api/v1/mcp/token",
        "https://registry.skillet.md/api/v1/mcp",
        "https://registry.skillet.md/api/v1/mcp/a/b",
        "https://registry.skillet.md/api/v1/mcp/%2e%2e%2fadmin",
        "https://user:pass@registry.skillet.md/api/v1/mcp/token",
        "https://registry.skillet.md:8443/api/v1/mcp/token",
        "https://registry.skillet.md/api/v1/mcp/token?debug=1",
        "https://registry.skillet.md/api/v1/mcp/token#fragment",
    ],
)
def test_endpoint_rejects_untrusted_urls(monkeypatch, url):
    monkeypatch.setenv("LEYRA_SKILLET_MCP_URL", url)
    with pytest.raises(leyra_skillet.SkilletError, match="invalid"):
        leyra_skillet._endpoint()


def test_endpoint_accepts_only_registry_hosted_https_link(monkeypatch):
    expected = "https://registry.skillet.md/api/v1/mcp/skillet_m_test-token"
    monkeypatch.setenv("LEYRA_SKILLET_MCP_URL", expected)
    assert leyra_skillet._endpoint() == expected


def test_decode_response_rejects_oversized_payload():
    response = httpx.Response(200, content=b"x" * (leyra_skillet.MAX_RESPONSE_BYTES + 1))
    with pytest.raises(leyra_skillet.SkilletError, match="1 MiB"):
        leyra_skillet._decode_response(response)


def test_decode_response_does_not_leak_remote_jsonrpc_error_text():
    response = httpx.Response(
        200,
        json={"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "secret-token"}},
    )
    with pytest.raises(leyra_skillet.SkilletError) as exc:
        leyra_skillet._decode_response(response)
    assert "secret-token" not in str(exc.value)


@pytest.mark.asyncio
async def test_mcp_initialize_list_and_tool_call(monkeypatch):
    monkeypatch.setenv(
        "LEYRA_SKILLET_MCP_URL",
        "https://registry.skillet.md/api/v1/mcp/skillet_m_test-token",
    )
    seen = []
    session = "test-session"

    def handler(request):
        payload = json.loads(request.content)
        seen.append((payload, request.headers))
        method = payload["method"]
        if method == "initialize":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": payload["id"], "result": {
                    "protocolVersion": "2025-06-18", "capabilities": {}, "serverInfo": {"name": "mock"}
                }},
                headers={"Mcp-Session-Id": session},
            )
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/list":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"], "result": {
                "tools": [{"name": "list_skills"}, {"name": "search"}, {"name": "get_skill"}]
            }})
        if method == "tools/call":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"], "result": {
                "content": [{"type": "text", "text": "skill list"}]
            }})
        return httpx.Response(400)

    original = leyra_skillet.httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original(*args, **kwargs)

    monkeypatch.setattr(leyra_skillet.httpx, "AsyncClient", client_factory)
    result = await leyra_skillet.call_skillet_tool("list_skills")
    assert result["content"][0]["text"] == "skill list"
    assert [item[0]["method"] for item in seen] == [
        "initialize", "notifications/initialized", "tools/list", "tools/call"
    ]
    assert seen[-1][0]["params"]["name"] == "list_skills"
    assert seen[-1][1]["mcp-session-id"] == session
    assert seen[-1][1]["mcp-protocol-version"] == "2025-06-18"


@pytest.mark.asyncio
async def test_mcp_maps_search_skills_to_search(monkeypatch):
    monkeypatch.setenv(
        "LEYRA_SKILLET_MCP_URL",
        "https://registry.skillet.md/api/v1/mcp/skillet_m_test-token",
    )
    calls = []

    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if payload["method"] == "initialize":
            return httpx.Response(200, json={"result": {"protocolVersion": "2025-06-18"}})
        if payload["method"] == "notifications/initialized":
            return httpx.Response(202)
        if payload["method"] == "tools/list":
            return httpx.Response(200, json={"result": {"tools": [{"name": "search"}]}})
        if payload["method"] == "tools/call":
            return httpx.Response(200, json={"result": {"content": []}})
        return httpx.Response(400)

    original = leyra_skillet.httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original(*args, **kwargs)

    monkeypatch.setattr(leyra_skillet.httpx, "AsyncClient", client_factory)
    await leyra_skillet.call_skillet_tool("search_skills", {"query": "python"})
    assert calls[-1]["params"]["name"] == "search"


@pytest.mark.asyncio
async def test_mcp_rejects_missing_tool_and_unknown_tool(monkeypatch):
    monkeypatch.setenv(
        "LEYRA_SKILLET_MCP_URL",
        "https://registry.skillet.md/api/v1/mcp/skillet_m_test-token",
    )

    def handler(request):
        payload = json.loads(request.content)
        if payload["method"] == "initialize":
            return httpx.Response(200, json={"result": {"protocolVersion": "2025-06-18"}})
        if payload["method"] == "notifications/initialized":
            return httpx.Response(202)
        return httpx.Response(200, json={"result": {"tools": []}})

    original = leyra_skillet.httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original(*args, **kwargs)

    monkeypatch.setattr(leyra_skillet.httpx, "AsyncClient", client_factory)
    with pytest.raises(leyra_skillet.SkilletError, match="Unsupported"):
        await leyra_skillet.call_skillet_tool("publish_skill")
    with pytest.raises(leyra_skillet.SkilletError, match="does not expose"):
        await leyra_skillet.call_skillet_tool("list_skills")


@pytest.mark.asyncio
async def test_skillet_model_tool_validates_arguments_without_network():
    result = await leyra_skillet.skillet_tool_text("get_skill", '{"slug": ""}')
    assert "error" in result


def test_remote_skillet_tools_are_gated_by_configuration(monkeypatch):
    from src import leyra_gateway

    monkeypatch.setattr(leyra_gateway, "discover_skills", lambda: {})
    monkeypatch.delenv("LEYRA_SKILLET_MCP_URL", raising=False)
    plain = leyra_gateway._prepare_skill_aware_payload({
        "model": "test-model",
        "messages": [{"role": "user", "content": "Find a skill."}],
    })
    assert "tools" not in plain

    monkeypatch.setenv(
        "LEYRA_SKILLET_MCP_URL",
        "https://registry.skillet.md/api/v1/mcp/skillet_m_test-token",
    )
    connected = leyra_gateway._prepare_skill_aware_payload({
        "model": "test-model",
        "messages": [{"role": "user", "content": "Find a skill."}],
    })
    names = {item["function"]["name"] for item in connected["tools"]}
    assert "leyra_skillet_list_skills" in names
    assert "leyra_skillet_search_skills" in names
    assert "leyra_skillet_get_skill" in names
    assert "read-only Skillet kit" in connected["messages"][0]["content"]


def test_skillet_gateway_routes_are_registered():
    from src.leyra_gateway import router

    paths = {route.path for route in router.routes}
    assert "/leyra/v1/skillet/skills" in paths
    assert "/leyra/v1/skillet/skills/{slug}" in paths
