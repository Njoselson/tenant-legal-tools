import pytest
from fastapi.testclient import TestClient

from tenant_legal_guidance.api.app import app


class _FakeAQL:
    def execute(self, *_args, **_kwargs):
        # Return minimal valid response for tests
        return [1]


class _FakeDB:
    def __init__(self):
        self.aql = _FakeAQL()

    def has_collection(self, _name: str) -> bool:
        return True


class _FakeKG:
    def __init__(self):
        self.db = _FakeDB()

    def _ensure_search_view(self):
        return None


class _FakeSystem:
    def __init__(self):
        self.knowledge_graph = _FakeKG()


@pytest.fixture(scope="module")
def client():
    # Disable lifespan to avoid real DB connections
    c = TestClient(app)
    # Inject a fake system used by health routes
    c.app.state.system = _FakeSystem()
    return c


def test_openapi_contains_routes(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    data = resp.json()
    # Check presence of key routes
    paths = data.get("paths", {})
    assert "/api/health" in paths
    assert "/api/health/search" in paths
    assert "/api/kg/expand" in paths


def test_health_search_contract(client, monkeypatch):
    # Mock minimal DB behavior on app.state.system if needed
    # Here we only check response shape; endpoint handles its own issues
    resp = client.get("/api/health/search")
    assert resp.status_code == 200
    body = resp.json()
    assert set(["status", "analyzers_ok", "view_ok", "fallback_ok"]).issubset(body.keys())
