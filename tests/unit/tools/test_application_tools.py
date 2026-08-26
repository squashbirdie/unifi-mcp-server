"""Unit tests for application tools.

Fixtures corrected to match a live response from the local Integration API
(Network 10.5.67, GET /proxy/network/integration/v1/info): the endpoint is
`/integration/v1/info`, NOT `/integration/v1/application/info` (which 404s),
and the response is only `{"applicationVersion": "..."}` — no build,
deploymentType, capabilities, or systemInfo fields exist there. The previous
version of this file encoded both mistakes.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.application as app_module
from src.tools.application import get_application_info


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    settings = MagicMock()
    settings.log_level = "INFO"
    settings.api_type = MagicMock()
    settings.api_type.value = "local"
    settings.base_url = "https://192.168.2.1"
    settings.api_key = "test-key"
    settings.local_host = "192.168.2.1"
    settings.local_port = 443
    settings.local_verify_ssl = False
    settings.get_integration_path = MagicMock(
        side_effect=lambda endpoint: f"/proxy/network/integration/v1/{endpoint.lstrip('/')}"
    )
    return settings


def _mock_client(response):
    mock_client = MagicMock()
    mock_client.is_authenticated = True
    mock_client.authenticate = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


@pytest.mark.asyncio
async def test_get_application_info_success(mock_settings):
    """Real endpoint, real response shape, real return value."""
    mock_client = _mock_client({"applicationVersion": "10.5.67"})

    with patch.object(app_module, "UniFiClient", return_value=mock_client):
        result = await get_application_info(settings=mock_settings)

    assert result == {"version": "10.5.67"}
    mock_client.get.assert_called_once_with("/proxy/network/integration/v1/info")


@pytest.mark.asyncio
async def test_get_application_info_wrapped_in_data(mock_settings):
    """Some UniFi endpoints wrap payloads in {"data": ...} — handle both."""
    mock_client = _mock_client({"data": {"applicationVersion": "10.5.67"}})

    with patch.object(app_module, "UniFiClient", return_value=mock_client):
        result = await get_application_info(settings=mock_settings)

    assert result == {"version": "10.5.67"}


@pytest.mark.asyncio
async def test_get_application_info_unauthenticated(mock_settings):
    """An unauthenticated client triggers authenticate() before the request."""
    mock_client = _mock_client({"applicationVersion": "10.5.67"})
    mock_client.is_authenticated = False

    with patch.object(app_module, "UniFiClient", return_value=mock_client):
        result = await get_application_info(settings=mock_settings)

    mock_client.authenticate.assert_called_once()
    assert result["version"] == "10.5.67"


@pytest.mark.asyncio
async def test_get_application_info_missing_field(mock_settings):
    """A response with no applicationVersion key yields version=None rather
    than raising — this endpoint has no other fields to fall back to."""
    mock_client = _mock_client({})

    with patch.object(app_module, "UniFiClient", return_value=mock_client):
        result = await get_application_info(settings=mock_settings)

    assert result == {"version": None}
