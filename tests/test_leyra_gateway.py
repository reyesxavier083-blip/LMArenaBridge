import pytest
from fastapi import HTTPException

from src.leyra_gateway import Settings, authorize, get_settings, upstream_headers, upstream_url


def test_get_settings_requires_gateway_token(monkeypatch):
    monkeypatch.setenv("LEYRA_UPSTREAM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.delenv("LEYRA_GATEWAY_TOKEN", raising=False)
    with pytest.raises(HTTPException) as error:
        get_settings()
    assert error.value.status_code == 503


def test_get_settings_rejects_remote_http(monkeypatch):
    monkeypatch.setenv("LEYRA_UPSTREAM_BASE_URL", "http://api.example.com/v1")
    monkeypatch.setenv("LEYRA_GATEWAY_TOKEN", "test-token")
    with pytest.raises(HTTPException) as error:
        get_settings()
    assert error.value.status_code == 503


def test_get_settings_allows_loopback_http(monkeypatch):
    monkeypatch.setenv("LEYRA_UPSTREAM_BASE_URL", "http://127.0.0.1:9000/v1")
    monkeypatch.setenv("LEYRA_GATEWAY_TOKEN", "test-token")
    settings = get_settings()
    assert settings.upstream_base_url == "http://127.0.0.1:9000/v1"


def test_authorize_uses_bearer_token():
    authorize("Bearer secret", "secret")
    with pytest.raises(HTTPException) as error:
        authorize("Bearer wrong", "secret")
    assert error.value.status_code == 401


def test_upstream_headers_do_not_expose_gateway_token():
    settings = Settings(
        upstream_base_url="https://api.example.com/v1",
        upstream_api_key="provider-secret",
        gateway_token="leyra-secret",
        timeout_seconds=90,
    )
    headers = upstream_headers(settings)
    assert headers["Authorization"] == "Bearer provider-secret"
    assert "leyra-secret" not in str(headers)


def test_upstream_url_joins_api_path():
    settings = Settings(
        upstream_base_url="https://api.example.com/v1/",
        upstream_api_key="",
        gateway_token="leyra-secret",
        timeout_seconds=90,
    )
    assert upstream_url(settings, "/models") == "https://api.example.com/v1/models"



def test_gateway_router_is_mounted_under_leyra_prefix():
    from src.leyra_gateway import router

    paths = {route.path for route in router.routes}
    assert "/leyra/health" in paths
    assert "/leyra/v1/models" in paths
    assert "/leyra/v1/chat/completions" in paths



@pytest.mark.asyncio
async def test_chat_endpoint_rejects_missing_bearer_token(monkeypatch):
    import httpx
    from src.leyra_gateway import app

    monkeypatch.setenv("LEYRA_UPSTREAM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("LEYRA_GATEWAY_TOKEN", "expected-token")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/leyra/v1/chat/completions",
            json={"model": "test-model", "messages": [{"role": "user", "content": "Hi"}]},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_endpoint_rejects_missing_messages(monkeypatch):
    import httpx
    from src.leyra_gateway import app

    monkeypatch.setenv("LEYRA_UPSTREAM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("LEYRA_GATEWAY_TOKEN", "expected-token")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/leyra/v1/chat/completions",
            headers={"Authorization": "Bearer expected-token"},
            json={"model": "test-model", "messages": []},
        )
    assert response.status_code == 400



@pytest.mark.asyncio
async def test_chat_endpoint_enforces_request_body_limit(monkeypatch):
    import httpx
    from src.leyra_gateway import app

    monkeypatch.setenv("LEYRA_UPSTREAM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("LEYRA_GATEWAY_TOKEN", "expected-token")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/leyra/v1/chat/completions",
            headers={"Authorization": "Bearer expected-token"},
            content=b"x" * (2 * 1024 * 1024 + 1),
        )
    assert response.status_code == 413



@pytest.mark.asyncio
async def test_connection_test_reaches_configured_provider(monkeypatch):
    import httpx
    from src.leyra_gateway import app

    monkeypatch.setenv("LEYRA_UPSTREAM_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("LEYRA_UPSTREAM_API_KEY", "provider-key")
    monkeypatch.setenv("LEYRA_GATEWAY_TOKEN", "client-token")

    real_async_client = httpx.AsyncClient

    class FakeProviderClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, headers):
            assert url == "https://provider.example/v1/models"
            assert headers["Authorization"] == "Bearer provider-key"
            return httpx.Response(200, json={"data": [{"id": "model-a"}]})

    monkeypatch.setattr(httpx, "AsyncClient", FakeProviderClient)
    transport = httpx.ASGITransport(app=app)
    async with real_async_client(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/leyra/connection/test",
            headers={"Authorization": "Bearer client-token"},
        )

    assert response.status_code == 200
    assert response.json()["connection"] == "connected"
    assert response.json()["provider_host"] == "provider.example"
    assert response.json()["api_key_configured"] is True


@pytest.mark.asyncio
async def test_connection_test_reports_provider_auth_failure(monkeypatch):
    import httpx
    from src.leyra_gateway import app

    monkeypatch.setenv("LEYRA_UPSTREAM_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("LEYRA_UPSTREAM_API_KEY", "bad-provider-key")
    monkeypatch.setenv("LEYRA_GATEWAY_TOKEN", "client-token")

    real_async_client = httpx.AsyncClient

    class FakeProviderClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, headers):
            return httpx.Response(401, json={"error": "invalid_api_key"})

    monkeypatch.setattr(httpx, "AsyncClient", FakeProviderClient)
    transport = httpx.ASGITransport(app=app)
    async with real_async_client(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/leyra/connection/test",
            headers={"Authorization": "Bearer client-token"},
        )

    assert response.status_code == 502
    assert "HTTP 401" in response.json()["detail"]
    assert "invalid_api_key" not in response.text
