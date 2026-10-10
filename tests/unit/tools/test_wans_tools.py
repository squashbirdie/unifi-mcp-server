"""Unit tests for WAN connection tools.

The local Integration v1 ``/sites/{siteId}/wans`` route returns only ``id`` and
``name``; a record must validate and must not be padded with values the
controller never reported.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.wans import list_wan_connections


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.log_level = "INFO"
    settings.api_type = MagicMock()
    settings.api_type.value = "local"
    return settings


def _client_returning(payload):
    client = AsyncMock()
    client.is_authenticated = True
    client.get = AsyncMock(return_value=payload)
    client.__aenter__.return_value = client
    return client


@pytest.mark.asyncio
async def test_sparse_response_reports_only_what_the_controller_sent(mock_settings):
    payload = {"data": [{"id": "a0eadfd4-03f6-455d-bf94-33a32169280e", "name": "Internet 1"}]}
    with patch("src.tools.wans.UniFiClient", return_value=_client_returning(payload)):
        result = await list_wan_connections("site-uuid", mock_settings)

    # No fabricated dns_servers=[] / is_backup=False: "unknown" must not look like "empty/false".
    assert result == [{"id": "a0eadfd4-03f6-455d-bf94-33a32169280e", "name": "Internet 1"}]


@pytest.mark.asyncio
async def test_explicit_falsy_values_are_kept(mock_settings):
    payload = [
        {
            "id": "w1",
            "name": "Internet 2",
            "dns_servers": [],
            "is_backup": False,
            "status": "online",
        }
    ]
    with patch("src.tools.wans.UniFiClient", return_value=_client_returning(payload)):
        result = await list_wan_connections("site-uuid", mock_settings)

    assert result[0]["dns_servers"] == []
    assert result[0]["is_backup"] is False
    assert result[0]["status"] == "online"
