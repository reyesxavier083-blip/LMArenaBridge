import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.leyra.api import initialize_services, router


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LEYRA_CONTROL_TOKEN", "test-control-token")
    monkeypatch.setenv("LEYRA_DATABASE_PATH", str(tmp_path / "leyra.sqlite3"))
    app = FastAPI()
    initialize_services(app)
    app.include_router(router)
    return TestClient(app)


def headers():
    return {"Authorization": "Bearer test-control-token"}


def test_health_is_public_and_reports_registered_agents(client):
    response = client.get("/leyra/core/health")
    assert response.status_code == 200
    assert response.json()["agents_registered"] >= 6


def test_control_api_rejects_missing_token(client):
    response = client.get("/leyra/core/agents")
    assert response.status_code == 401


def test_planner_agent_dispatch(client):
    response = client.post(
        "/leyra/core/tasks",
        headers=headers(),
        json={"agent": "planner", "payload": {"objective": "Audit the API"}},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "planned"
    assert len(response.json()["data"]["steps"]) >= 3


def test_memory_round_trip(client):
    saved = client.post(
        "/leyra/core/memory",
        headers=headers(),
        json={"namespace": "project", "content": "LEYRA cloud core initialized"},
    )
    assert saved.status_code == 200
    items = client.get("/leyra/core/memory?namespace=project", headers=headers())
    assert items.status_code == 200
    assert items.json()["items"][0]["content"] == "LEYRA cloud core initialized"


def test_unconfigured_agent_does_not_claim_execution(client):
    response = client.post(
        "/leyra/core/tasks",
        headers=headers(),
        json={"agent": "vision", "payload": {"input": "image"}},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "not_configured"
    assert response.json()["data"]["external_action_executed"] is False

def test_combined_cloud_app_mounts_core_and_provider_gateway():
    from src.leyra.app import app

    paths = {route.path for route in app.routes}
    assert "/leyra/core/health" in paths
    assert "/leyra/health" in paths
    assert "/leyra/connection/test" in paths
    assert "/leyra/v1/models" in paths
    assert "/leyra/v1/chat/completions" in paths




def test_sqlite_storage_health_and_audit(client):
    health = client.get("/leyra/core/health")
    assert health.status_code == 200
    assert health.json()["storage"] == {"database": "sqlite", "cache": "disabled"}

    saved = client.post("/leyra/core/memory", headers=headers(),
                        json={"namespace": "checks", "content": "persisted"})
    assert saved.status_code == 200
    audit = client.get("/leyra/core/audit", headers=headers())
    assert audit.status_code == 200
    assert audit.json()["events"][0]["event_type"] == "memory.write"
