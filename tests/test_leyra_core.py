import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.leyra.api import initialize_services, router


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LEYRA_CONTROL_TOKEN", "test-control-token")
    monkeypatch.setenv("LEYRA_JWT_SECRET", "test-jwt-secret-that-is-long-enough")
    monkeypatch.setenv("LEYRA_BOOTSTRAP_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("LEYRA_BOOTSTRAP_ADMIN_PASSWORD", "test-admin-password-123")
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


def test_admin_login_and_role_protected_user_creation(client):
    login = client.post("/leyra/core/auth/login", json={"email": "admin@example.com", "password": "test-admin-password-123"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    created = client.post("/leyra/core/users", headers={"Authorization": "Bearer " + token},
        json={"email": "viewer@example.com", "password": "viewer-password-123", "role": "viewer"})
    assert created.status_code == 201
    viewer_login = client.post("/leyra/core/auth/login", json={"email": "viewer@example.com", "password": "viewer-password-123"})
    assert viewer_login.status_code == 200
    viewer_token = viewer_login.json()["access_token"]
    denied = client.get("/leyra/core/audit", headers={"Authorization": "Bearer " + viewer_token})
    assert denied.status_code == 403
    allowed = client.get("/leyra/core/agents", headers={"Authorization": "Bearer " + viewer_token})
    assert allowed.status_code == 200


def test_model_routes_require_auth_and_report_unconfigured_provider(client, monkeypatch):
    monkeypatch.delenv("LEYRA_UPSTREAM_BASE_URL", raising=False)
    no_auth = client.get("/leyra/core/models")
    assert no_auth.status_code == 401
    unavailable = client.get("/leyra/core/models", headers=headers())
    assert unavailable.status_code == 503
    chat = client.post("/leyra/core/chat", headers=headers(),
        json={"model": "example-model", "messages": [{"role": "user", "content": "Hola"}]})
    assert chat.status_code == 503


def test_memory_search_ranks_relevant_context(client):
    for content in ["LEYRA usa PostgreSQL y Redis", "La interfaz tiene un tema azul", "El motor de razonamiento recupera memoria contextual"]: 
        saved = client.post("/leyra/core/memory", headers=headers(),
            json={"namespace": "reasoning", "content": content})
        assert saved.status_code == 200
    result = client.get("/leyra/core/memory/search?query=razonamiento%20memoria&namespace=reasoning&limit=3", headers=headers())
    assert result.status_code == 200
    assert "razonamiento" in result.json()["items"][0]["content"].lower()


def test_memory_search_requires_auth(client):
    result = client.get("/leyra/core/memory/search?query=LEYRA")
    assert result.status_code == 401


def test_memory_is_isolated_between_authenticated_users(client):
    admin_login = client.post("/leyra/core/auth/login", json={"email": "admin@example.com", "password": "test-admin-password-123"})
    admin_token = admin_login.json()["access_token"]
    created = client.post("/leyra/core/users", headers={"Authorization": "Bearer " + admin_token},
        json={"email": "alice@example.com", "password": "alice-password-123", "role": "operator"})
    assert created.status_code == 201
    alice_login = client.post("/leyra/core/auth/login", json={"email": "alice@example.com", "password": "alice-password-123"})
    alice_token = alice_login.json()["access_token"]
    alice_headers = {"Authorization": "Bearer " + alice_token}
    saved = client.post("/leyra/core/memory", headers=alice_headers,
        json={"namespace": "private", "content": "Alice private project memory"})
    assert saved.status_code == 200
    admin_read = client.get("/leyra/core/memory?namespace=private", headers=headers())
    assert admin_read.status_code == 200
    assert admin_read.json()["items"] == []
    alice_read = client.get("/leyra/core/memory?namespace=private", headers=alice_headers)
    assert alice_read.json()["items"][0]["content"] == "Alice private project memory"
    admin_search = client.get("/leyra/core/memory/search?query=Alice&namespace=private", headers=headers())
    assert admin_search.json()["items"] == []


def test_vector_memory_uses_cosine_similarity_and_owner_scope(tmp_path):
    from src.leyra.storage import Storage

    storage = Storage(database_path=str(tmp_path / "vectors.sqlite3"))
    first = storage.save_memory("semantic", "El proyecto trata sobre inteligencia artificial", owner_id="user-a")
    second = storage.save_memory("semantic", "Receta de pan y cocina", owner_id="user-a")
    storage.save_embedding(first, "user-a", "semantic", "test-embedding", [1.0, 0.0, 0.0])
    storage.save_embedding(second, "user-a", "semantic", "test-embedding", [0.0, 1.0, 0.0])

    result = storage.search_memory_vector([0.9, 0.1, 0.0], "semantic", 2,
                                          owner_id="user-a", model="test-embedding")
    assert result[0]["id"] == first
    assert result[0]["retrieval"] == "vector"
    assert result[0]["score"] > result[1]["score"]
    assert storage.search_memory_vector([1.0, 0.0, 0.0], "semantic", 5,
                                        owner_id="user-b", model="test-embedding") == []


def test_vector_memory_rejects_dimension_mismatch(tmp_path):
    from src.leyra.storage import Storage

    storage = Storage(database_path=str(tmp_path / "dimensions.sqlite3"))
    memory_id = storage.save_memory("semantic", "test", owner_id="user-a")
    storage.save_embedding(memory_id, "user-a", "semantic", "test-model", [1.0, 0.0])
    result = storage.search_memory_vector([1.0, 0.0, 0.0], "semantic", 5,
                                          owner_id="user-a", model="test-model")
    assert result == []
