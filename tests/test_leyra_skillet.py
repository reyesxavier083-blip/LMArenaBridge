import pytest

from src import leyra_skillet


def test_skillet_endpoint_requires_private_configuration(monkeypatch):
    monkeypatch.delenv("LEYRA_SKILLET_MCP_URL", raising=False)
    with pytest.raises(leyra_skillet.SkilletError, match="not configured"):
        leyra_skillet._endpoint()


def test_skillet_endpoint_accepts_only_registry_hosted_mcp_link(monkeypatch):
    monkeypatch.setenv(
        "LEYRA_SKILLET_MCP_URL",
        "https://registry.skillet.md/api/v1/mcp/skillet_m_test-token",
    )
    assert leyra_skillet._endpoint().startswith("https://registry.skillet.md/api/v1/mcp/")


@pytest.mark.parametrize(
    "url",
    [
        "http://registry.skillet.md/api/v1/mcp/token",
        "https://example.com/api/v1/mcp/token",
        "https://registry.skillet.md.evil.test/api/v1/mcp/token",
        "https://registry.skillet.md/api/v1/mcp",
        "https://user:pass@registry.skillet.md/api/v1/mcp/token",
    ],
)
def test_skillet_endpoint_rejects_untrusted_urls(monkeypatch, url):
    monkeypatch.setenv("LEYRA_SKILLET_MCP_URL", url)
    with pytest.raises(leyra_skillet.SkilletError, match="invalid"):
        leyra_skillet._endpoint()


@pytest.mark.asyncio
async def test_skillet_tool_rejects_unknown_tools(monkeypatch):
    monkeypatch.setenv(
        "LEYRA_SKILLET_MCP_URL",
        "https://registry.skillet.md/api/v1/mcp/skillet_m_test-token",
    )
    with pytest.raises(leyra_skillet.SkilletError, match="Unsupported"):
        await leyra_skillet.call_skillet_tool("publish_skill")


@pytest.mark.asyncio
async def test_skillet_model_tool_validates_arguments_without_network():
    result = await leyra_skillet.skillet_tool_text("get_skill", '{"slug": ""}')
    assert "error" in result
