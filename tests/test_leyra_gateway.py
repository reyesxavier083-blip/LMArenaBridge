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
