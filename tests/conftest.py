import os
import pytest
from unittest.mock import MagicMock, patch
from tenant_legal_guidance.services.deepseek import DeepSeekClient

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