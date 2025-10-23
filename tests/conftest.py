import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tenant_legal_guidance.api.app import app
from tenant_legal_guidance.services.deepseek import DeepSeekClient
from tenant_legal_guidance.services.tenant_system import TenantLegalSystem


@pytest.fixture
def mock_response():
    """Create a mock response for HTTP requests."""
    mock = MagicMock()
    mock.status_code = 200
    mock.text = """
    <html>
        <body>
            <h1>Housing Rights</h1>
            <div class="content">
                <p>Tenants have the right to safe and habitable housing.</p>
                <p>Landlords must maintain the property in good condition.</p>
                <ul>
                    <li>Repair requests must be addressed within 24 hours</li>
                    <li>Rent increases are limited to 5% per year</li>
                </ul>
            </div>
        </body>
    </html>
    """
    return mock


@pytest.fixture
def deepseek_client():
    """Create a test instance of DeepSeekClient."""
    return DeepSeekClient("test_api_key")


@pytest.fixture
def client_with_fake_system(monkeypatch):
    """FastAPI TestClient with dependency_overrides-style injection using app.state.

    Example usage:
        def test_route(client_with_fake_system):
            resp = client_with_fake_system.get("/api/health")
            assert resp.status_code == 200
    """

    class FakeSystem(TenantLegalSystem):
        def __init__(self): ...

    fake_system = FakeSystem()

    # Override app.state before startup
    def _override_lifespan_state():
        app.state.system = fake_system
        return app

    # In tests, ensure state is set (works even with lifespan)
    _override_lifespan_state()
    with TestClient(app) as c:
        yield c
