"""Tests for Traffic Matching Lists tools.

Fixtures use the real integration API shape (developer.ui.com/network v10.4.57, verified
2026-08-26): `id` (not `_id`), PORTS items are `{"type": "PORT_NUMBER", "value": <int>}`
(not `{"type": "PORT", "value": <str>}`), and IPv4/IPv6 items both use `IP_ADDRESS`/
`SUBNET` (not a nonexistent `IPV6_ADDRESS` type) - the previous fixtures used none of these
correctly, which is exactly why `list_traffic_matching_lists` failed validation on a live
controller despite this test file passing.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pydantic
import pytest

import src.tools.traffic_matching_lists as tml_module
from src.tools.traffic_matching_lists import (
    create_traffic_matching_list,
    delete_traffic_matching_list,
    get_traffic_matching_list,
    list_traffic_matching_lists,
    update_traffic_matching_list,
)
from src.utils.exceptions import ResourceNotFoundError, ValidationError


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.log_level = "INFO"
    settings.api_type = MagicMock()
    settings.api_type.value = "cloud-ea"
    settings.base_url = "https://192.168.2.1"
    settings.api_key = "test-key"
    settings.local_host = "192.168.2.1"
    settings.local_port = 443
    settings.local_verify_ssl = False
    settings.request_timeout = 30.0
    settings.site_manager_enabled = False
    settings.get_headers = MagicMock(return_value={"X-API-Key": "test-key"})
    settings.get_integration_path = MagicMock(
        side_effect=lambda endpoint: f"/integration/v1/{endpoint}"
    )
    return settings


@pytest.mark.asyncio
async def test_list_traffic_matching_lists_success(mock_settings):
    mock_response = {
        "data": [
            {
                "id": "tml-1",
                "type": "PORTS",
                "name": "Web Ports",
                "items": [
                    {"type": "PORT_NUMBER", "value": 80},
                    {"type": "PORT_NUMBER", "value": 443},
                    {"type": "PORT_NUMBER_RANGE", "start": 8000, "stop": 8100},
                ],
                "site_id": "default",
            },
            {
                "id": "tml-2",
                "type": "IPV4_ADDRESSES",
                "name": "Blocked IPs",
                "items": [
                    {"type": "IP_ADDRESS", "value": "10.0.0.1"},
                    {"type": "SUBNET", "value": "10.0.0.0/24"},
                ],
                "site_id": "default",
            },
        ]
    }

    with patch("src.tools.traffic_matching_lists.UniFiClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.authenticate = AsyncMock()
        mock_client.resolve_site_id = AsyncMock(return_value="default")
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await list_traffic_matching_lists("default", mock_settings)

        assert len(result) == 2
        assert result[0]["id"] == "tml-1"
        assert result[0]["type"] == "PORTS"
        assert result[0]["name"] == "Web Ports"
        assert result[0]["items"][0]["value"] == 80
        assert result[0]["items"][2]["start"] == 8000
        assert result[1]["id"] == "tml-2"
        assert result[1]["type"] == "IPV4_ADDRESSES"


@pytest.mark.asyncio
async def test_list_traffic_matching_lists_pagination(mock_settings):
    mock_response = {
        "data": [
            {
                "id": f"tml-{i}",
                "type": "PORTS",
                "name": f"List {i}",
                "items": [{"type": "PORT_NUMBER", "value": 80}],
            }
            for i in range(1, 11)
        ]
    }

    with patch("src.tools.traffic_matching_lists.UniFiClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.authenticate = AsyncMock()
        mock_client.resolve_site_id = AsyncMock(return_value="default")
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await list_traffic_matching_lists("default", mock_settings, limit=5, offset=4)

        assert len(result) == 5
        assert result[0]["id"] == "tml-5"
        assert result[4]["id"] == "tml-9"


@pytest.mark.asyncio
async def test_list_traffic_matching_lists_empty(mock_settings):
    mock_response = {"data": []}

    with patch("src.tools.traffic_matching_lists.UniFiClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.authenticate = AsyncMock()
        mock_client.resolve_site_id = AsyncMock(return_value="default")
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await list_traffic_matching_lists("default", mock_settings)

        assert result == []


@pytest.mark.asyncio
async def test_get_traffic_matching_list_success(mock_settings):
    mock_response = {
        "data": {
            "id": "tml-1",
            "type": "PORTS",
            "name": "Web Ports",
            "items": [
                {"type": "PORT_NUMBER", "value": 80},
                {"type": "PORT_NUMBER", "value": 443},
                {"type": "PORT_NUMBER", "value": 8080},
                {"type": "PORT_NUMBER", "value": 8443},
            ],
            "site_id": "default",
        }
    }

    with patch("src.tools.traffic_matching_lists.UniFiClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.authenticate = AsyncMock()
        mock_client.resolve_site_id = AsyncMock(return_value="default")
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await get_traffic_matching_list("default", "tml-1", mock_settings)

        assert result["id"] == "tml-1"
        assert result["name"] == "Web Ports"
        assert len(result["items"]) == 4


@pytest.mark.asyncio
async def test_get_traffic_matching_list_direct_response(mock_settings):
    mock_response = {
        "id": "tml-1",
        "type": "IPV6_ADDRESSES",
        "name": "IPv6 List",
        "items": [
            {"type": "IP_ADDRESS", "value": "2001:db8::1"},
            {"type": "SUBNET", "value": "2001:db8::/32"},
        ],
    }

    with patch("src.tools.traffic_matching_lists.UniFiClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.authenticate = AsyncMock()
        mock_client.resolve_site_id = AsyncMock(return_value="default")
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await get_traffic_matching_list("default", "tml-1", mock_settings)

        assert result["id"] == "tml-1"
        assert result["type"] == "IPV6_ADDRESSES"


@pytest.mark.asyncio
async def test_get_traffic_matching_list_not_found(mock_settings):
    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.resolve_site_id = AsyncMock(return_value="default")
    mock_client.get = AsyncMock(return_value={})
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch.object(tml_module, "UniFiClient", return_value=mock_client):
        with pytest.raises(ResourceNotFoundError):
            await get_traffic_matching_list("default", "tml-nonexistent", mock_settings)


@pytest.mark.asyncio
async def test_create_traffic_matching_list_success(mock_settings):
    mock_response = {
        "data": {
            "id": "tml-new",
            "type": "PORTS",
            "name": "New Port List",
            "items": [
                {"type": "PORT_NUMBER", "value": 22},
                {"type": "PORT_NUMBER", "value": 80},
                {"type": "PORT_NUMBER", "value": 443},
            ],
            "site_id": "default",
        }
    }

    with patch("src.tools.traffic_matching_lists.UniFiClient") as mock_client_class:
        with patch("src.tools.traffic_matching_lists.log_audit"):
            mock_client = AsyncMock()
            mock_client.authenticate = AsyncMock()
            mock_client.resolve_site_id = AsyncMock(return_value="default")
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await create_traffic_matching_list(
                "default",
                "PORTS",
                "New Port List",
                [22, 80, 443],
                mock_settings,
                confirm=True,
            )

            assert result["id"] == "tml-new"
            assert result["name"] == "New Port List"
            mock_client.post.assert_called_once()
            payload = mock_client.post.call_args[1]["json_data"]
            assert payload["items"] == [
                {"type": "PORT_NUMBER", "value": 22},
                {"type": "PORT_NUMBER", "value": 80},
                {"type": "PORT_NUMBER", "value": 443},
            ]


@pytest.mark.asyncio
async def test_create_traffic_matching_list_port_range(mock_settings):
    """Range items ({"start", "stop"}) are the reason the old flat-string item model
    couldn't have worked - there is no single "value" for a range at all."""
    mock_response = {
        "data": {
            "id": "tml-range",
            "type": "PORTS",
            "name": "Ephemeral Range",
            "items": [{"type": "PORT_NUMBER_RANGE", "start": 32768, "stop": 60999}],
        }
    }

    with patch("src.tools.traffic_matching_lists.UniFiClient") as mock_client_class:
        with patch("src.tools.traffic_matching_lists.log_audit"):
            mock_client = AsyncMock()
            mock_client.authenticate = AsyncMock()
            mock_client.resolve_site_id = AsyncMock(return_value="default")
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await create_traffic_matching_list(
                "default",
                "PORTS",
                "Ephemeral Range",
                [{"start": 32768, "stop": 60999}],
                mock_settings,
                confirm=True,
            )

            assert result["items"][0]["start"] == 32768
            payload = mock_client.post.call_args[1]["json_data"]
            assert payload["items"] == [
                {"type": "PORT_NUMBER_RANGE", "start": 32768, "stop": 60999}
            ]


@pytest.mark.asyncio
async def test_create_traffic_matching_list_subnet_autodetect(mock_settings):
    """A '/' in a string item auto-selects SUBNET over IP_ADDRESS."""
    mock_response = {
        "data": {
            "id": "tml-subnet",
            "type": "IPV4_ADDRESSES",
            "name": "Mixed",
            "items": [
                {"type": "IP_ADDRESS", "value": "10.0.1.193"},
                {"type": "SUBNET", "value": "10.0.10.0/24"},
            ],
        }
    }

    with patch("src.tools.traffic_matching_lists.UniFiClient") as mock_client_class:
        with patch("src.tools.traffic_matching_lists.log_audit"):
            mock_client = AsyncMock()
            mock_client.authenticate = AsyncMock()
            mock_client.resolve_site_id = AsyncMock(return_value="default")
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            await create_traffic_matching_list(
                "default",
                "IPV4_ADDRESSES",
                "Mixed",
                ["10.0.1.193", "10.0.10.0/24"],
                mock_settings,
                confirm=True,
            )

            payload = mock_client.post.call_args[1]["json_data"]
            assert payload["items"] == [
                {"type": "IP_ADDRESS", "value": "10.0.1.193"},
                {"type": "SUBNET", "value": "10.0.10.0/24"},
            ]


@pytest.mark.asyncio
async def test_create_traffic_matching_list_dry_run(mock_settings):
    with patch("src.tools.traffic_matching_lists.log_audit"):
        result = await create_traffic_matching_list(
            "default",
            "IPV4_ADDRESSES",
            "Test IPs",
            ["192.168.2.1", "192.168.1.2"],
            mock_settings,
            confirm=True,
            dry_run=True,
        )

        assert result["dry_run"] is True
        assert result["would_create"]["name"] == "Test IPs"
        assert result["would_create"]["type"] == "IPV4_ADDRESSES"
        assert result["would_create"]["items"] == [
            {"type": "IP_ADDRESS", "value": "192.168.2.1"},
            {"type": "IP_ADDRESS", "value": "192.168.1.2"},
        ]


@pytest.mark.asyncio
async def test_create_traffic_matching_list_no_confirm(mock_settings):
    with pytest.raises(ValidationError) as excinfo:
        await create_traffic_matching_list(
            "default",
            "PORTS",
            "Test",
            [80],
            mock_settings,
            confirm=False,
        )
    assert "requires confirmation" in str(excinfo.value)


@pytest.mark.asyncio
async def test_create_traffic_matching_list_invalid_type(mock_settings):
    with pytest.raises(ValidationError) as excinfo:
        await create_traffic_matching_list(
            "default",
            "INVALID_TYPE",
            "Test",
            [80],
            mock_settings,
            confirm=True,
        )
    assert "Invalid list type" in str(excinfo.value)


@pytest.mark.asyncio
async def test_create_traffic_matching_list_empty_items(mock_settings):
    with pytest.raises(ValidationError) as excinfo:
        await create_traffic_matching_list(
            "default",
            "PORTS",
            "Test",
            [],
            mock_settings,
            confirm=True,
        )
    assert "cannot be empty" in str(excinfo.value)


@pytest.mark.asyncio
async def test_create_traffic_matching_list_out_of_range_port(mock_settings):
    """The real per-item schema is enforced, not just a flat string check."""
    with patch("src.tools.traffic_matching_lists.log_audit"):
        with pytest.raises(pydantic.ValidationError):
            await create_traffic_matching_list(
                "default",
                "PORTS",
                "Bad Port",
                [70000],
                mock_settings,
                confirm=True,
                dry_run=True,
            )


@pytest.mark.asyncio
async def test_update_traffic_matching_list_success(mock_settings):
    mock_get_response = {
        "data": {
            "id": "tml-1",
            "type": "PORTS",
            "name": "Old Name",
            "items": [{"type": "PORT_NUMBER", "value": 80}],
        }
    }
    mock_put_response = {
        "data": {
            "id": "tml-1",
            "type": "PORTS",
            "name": "New Name",
            "items": [
                {"type": "PORT_NUMBER", "value": 80},
                {"type": "PORT_NUMBER", "value": 443},
            ],
        }
    }

    with patch("src.tools.traffic_matching_lists.UniFiClient") as mock_client_class:
        with patch("src.tools.traffic_matching_lists.log_audit"):
            mock_client = AsyncMock()
            mock_client.authenticate = AsyncMock()
            mock_client.resolve_site_id = AsyncMock(return_value="default")
            mock_client.get = AsyncMock(return_value=mock_get_response)
            mock_client.put = AsyncMock(return_value=mock_put_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await update_traffic_matching_list(
                "default",
                "tml-1",
                mock_settings,
                name="New Name",
                items=[80, 443],
                confirm=True,
            )

            assert result["name"] == "New Name"
            mock_client.put.assert_called_once()
            payload = mock_client.put.call_args[1]["json_data"]
            assert payload["items"] == [
                {"type": "PORT_NUMBER", "value": 80},
                {"type": "PORT_NUMBER", "value": 443},
            ]


@pytest.mark.asyncio
async def test_update_traffic_matching_list_dry_run(mock_settings):
    with patch("src.tools.traffic_matching_lists.log_audit"):
        result = await update_traffic_matching_list(
            "default",
            "tml-1",
            mock_settings,
            name="Updated Name",
            confirm=True,
            dry_run=True,
        )

        assert result["dry_run"] is True
        assert result["would_update"]["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_update_traffic_matching_list_no_confirm(mock_settings):
    with pytest.raises(ValidationError) as excinfo:
        await update_traffic_matching_list(
            "default",
            "tml-1",
            mock_settings,
            name="New Name",
            confirm=False,
        )
    assert "requires confirmation" in str(excinfo.value)


@pytest.mark.asyncio
async def test_update_traffic_matching_list_invalid_type(mock_settings):
    with pytest.raises(ValidationError) as excinfo:
        await update_traffic_matching_list(
            "default",
            "tml-1",
            mock_settings,
            list_type="INVALID",
            confirm=True,
        )
    assert "Invalid list type" in str(excinfo.value)


@pytest.mark.asyncio
async def test_update_traffic_matching_list_empty_items(mock_settings):
    with pytest.raises(ValidationError) as excinfo:
        await update_traffic_matching_list(
            "default",
            "tml-1",
            mock_settings,
            items=[],
            confirm=True,
        )
    assert "cannot be empty" in str(excinfo.value)


@pytest.mark.asyncio
async def test_update_traffic_matching_list_not_found(mock_settings):
    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.resolve_site_id = AsyncMock(return_value="default")
    mock_client.get = AsyncMock(return_value={})
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch.object(tml_module, "UniFiClient", return_value=mock_client):
        with patch.object(tml_module, "log_audit"):
            with pytest.raises(ResourceNotFoundError):
                await update_traffic_matching_list(
                    "default",
                    "tml-nonexistent",
                    mock_settings,
                    name="New Name",
                    confirm=True,
                )


@pytest.mark.asyncio
async def test_delete_traffic_matching_list_success(mock_settings):
    mock_get_response = {
        "data": {
            "id": "tml-1",
            "type": "PORTS",
            "name": "To Delete",
            "items": [{"type": "PORT_NUMBER", "value": 80}],
        }
    }
    mock_delete_response = {}

    with patch("src.tools.traffic_matching_lists.UniFiClient") as mock_client_class:
        with patch("src.tools.traffic_matching_lists.log_audit"):
            mock_client = AsyncMock()
            mock_client.authenticate = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_get_response)
            mock_client.delete = AsyncMock(return_value=mock_delete_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await delete_traffic_matching_list(
                "default",
                "tml-1",
                mock_settings,
                confirm=True,
            )

            assert result["success"] is True
            assert result["deleted_list_id"] == "tml-1"
            mock_client.delete.assert_called_once()


@pytest.mark.asyncio
async def test_delete_traffic_matching_list_dry_run(mock_settings):
    with patch("src.tools.traffic_matching_lists.log_audit"):
        result = await delete_traffic_matching_list(
            "default",
            "tml-1",
            mock_settings,
            confirm=True,
            dry_run=True,
        )

        assert result["dry_run"] is True
        assert result["would_delete"] == "tml-1"


@pytest.mark.asyncio
async def test_delete_traffic_matching_list_no_confirm(mock_settings):
    with pytest.raises(ValidationError) as excinfo:
        await delete_traffic_matching_list(
            "default",
            "tml-1",
            mock_settings,
            confirm=False,
        )
    assert "requires confirmation" in str(excinfo.value)


@pytest.mark.asyncio
async def test_delete_traffic_matching_list_not_found(mock_settings):
    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.resolve_site_id = AsyncMock(return_value="default")
    mock_client.get = AsyncMock(side_effect=Exception("Not found"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch.object(tml_module, "UniFiClient", return_value=mock_client):
        with patch.object(tml_module, "log_audit"):
            with pytest.raises(ResourceNotFoundError):
                await delete_traffic_matching_list(
                    "default",
                    "tml-nonexistent",
                    mock_settings,
                    confirm=True,
                )
