"""Tests for ACL tools.

Fixtures use the real integration API shape (developer.ui.com/network v10.4.57, verified
2026-08-26): camelCase `sourceFilter`/`destinationFilter` discriminated objects, `metadata`,
`index`, `type` (IPV4/MAC) - not the flat guessed shape (`source_type`, `dst_port`, ...)
this test file used before that field never existed in the real API.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.acls import (
    create_acl_rule,
    delete_acl_rule,
    get_acl_rule,
    list_acl_rules,
    update_acl_rule,
)
from src.utils.exceptions import ValidationError


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


def _prepare_client(mock_client: AsyncMock) -> AsyncMock:
    """Mock resolve_site_id so tests can assert literal paths."""
    mock_client.resolve_site_id = AsyncMock(side_effect=lambda s: s)
    return mock_client


def _ip_rule(**overrides):
    rule = {
        "id": "acl-1",
        "type": "IPV4",
        "index": 10,
        "name": "Block IoT to LAN",
        "enabled": True,
        "action": "BLOCK",
        "metadata": {"origin": "USER_DEFINED"},
        "sourceFilter": {"type": "NETWORKS", "networkIds": ["net-iot"]},
        "destinationFilter": {"type": "NETWORKS", "networkIds": ["net-lan"]},
    }
    rule.update(overrides)
    return rule


@pytest.mark.asyncio
async def test_list_acl_rules_success(mock_settings):
    mock_response = {
        "data": [
            _ip_rule(),
            {
                "id": "acl-2",
                "type": "IPV4",
                "index": 20,
                "name": "Allow DNS",
                "enabled": True,
                "action": "ALLOW",
                "metadata": {"origin": "USER_DEFINED"},
                "destinationFilter": {"type": "PORTS", "portFilter": [53]},
                "protocolFilter": ["UDP"],
            },
        ]
    }

    with patch("src.tools.acls.UniFiClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.is_authenticated = False
        mock_client.authenticate = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await list_acl_rules("default", mock_settings)

        assert len(result) == 2
        assert result[0]["id"] == "acl-1"
        assert result[0]["name"] == "Block IoT to LAN"
        assert result[0]["action"] == "BLOCK"
        assert result[0]["source_filter"]["network_ids"] == ["net-iot"]
        assert result[1]["id"] == "acl-2"
        assert result[1]["protocol_filter"] == ["UDP"]
        mock_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_list_acl_rules_with_filter(mock_settings):
    mock_response = {"data": [_ip_rule(action="BLOCK")]}

    with patch("src.tools.acls.UniFiClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.is_authenticated = True
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await list_acl_rules("default", mock_settings, filter_expr="action==BLOCK")

        assert len(result) == 1
        assert result[0]["action"] == "BLOCK"
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert call_args[1]["params"]["filter"] == "action==BLOCK"


@pytest.mark.asyncio
async def test_list_acl_rules_pagination(mock_settings):
    mock_response = {"data": [_ip_rule(id="acl-5", index=50, name="Rule 5")]}

    with patch("src.tools.acls.UniFiClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.is_authenticated = True
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await list_acl_rules("default", mock_settings, limit=10, offset=4)

        assert len(result) == 1
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert call_args[1]["params"]["limit"] == 10
        assert call_args[1]["params"]["offset"] == 4


@pytest.mark.asyncio
async def test_list_acl_rules_empty(mock_settings):
    mock_response = {"data": []}

    with patch("src.tools.acls.UniFiClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.is_authenticated = True
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await list_acl_rules("default", mock_settings)

        assert result == []


@pytest.mark.asyncio
async def test_get_acl_rule_success(mock_settings):
    mock_response = {
        "data": _ip_rule(
            name="Block IoT",
            description="Isolate IoT devices",
            destinationFilter={
                "type": "IP_ADDRESSES_OR_SUBNETS",
                "ipAddressesOrSubnets": ["10.0.1.193"],
                "portFilter": [8123],
            },
        )
    }

    with patch("src.tools.acls.UniFiClient") as mock_client_class:
        mock_client = _prepare_client(AsyncMock())
        mock_client.is_authenticated = False
        mock_client.authenticate = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await get_acl_rule("default", "acl-1", mock_settings)

        assert result["id"] == "acl-1"
        assert result["name"] == "Block IoT"
        assert result["description"] == "Isolate IoT devices"
        assert result["destination_filter"]["ip_addresses_or_subnets"] == ["10.0.1.193"]
        assert result["destination_filter"]["port_filter"] == [8123]
        mock_client.get.assert_called_once_with("/integration/v1/sites/default/acl-rules/acl-1")


@pytest.mark.asyncio
async def test_get_acl_rule_direct_response(mock_settings):
    mock_response = _ip_rule(name="Direct Rule", action="ALLOW")

    with patch("src.tools.acls.UniFiClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.is_authenticated = True
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await get_acl_rule("default", "acl-1", mock_settings)

        assert result["id"] == "acl-1"
        assert result["name"] == "Direct Rule"


@pytest.mark.asyncio
async def test_create_acl_rule_success(mock_settings):
    mock_response = {"data": _ip_rule(id="acl-new", name="New ACL Rule", action="ALLOW")}

    with patch("src.tools.acls.UniFiClient") as mock_client_class:
        with patch("src.tools.acls.audit_action", new_callable=AsyncMock) as mock_audit:
            mock_client = AsyncMock()
            mock_client.is_authenticated = False
            mock_client.authenticate = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await create_acl_rule(
                "default",
                "New ACL Rule",
                "allow",
                mock_settings,
                confirm=True,
            )

            assert result["id"] == "acl-new"
            assert result["name"] == "New ACL Rule"
            mock_client.post.assert_called_once()
            mock_audit.assert_called_once()


@pytest.mark.asyncio
async def test_create_acl_rule_with_network_filter(mock_settings):
    """Real source/destination filters, the whole point of the fix — these are NOT
    dropped, unlike the field names this test previously tried (`source_network`, ...)."""
    mock_response = {"data": _ip_rule(id="acl-net", name="Infra to HomeAssistant")}

    with patch("src.tools.acls.UniFiClient") as mock_client_class:
        with patch("src.tools.acls.audit_action", new_callable=AsyncMock):
            mock_client = AsyncMock()
            mock_client.is_authenticated = True
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            await create_acl_rule(
                "default",
                "Infra to HomeAssistant",
                "allow",
                mock_settings,
                source_network_ids=["net-infra"],
                destination_ip_addresses_or_subnets=["10.0.1.193"],
                destination_port_filter=[8123],
                protocol_filter=["tcp"],
                confirm=True,
            )

            payload = mock_client.post.call_args[1]["json_data"]
            assert payload["sourceFilter"] == {"type": "NETWORKS", "networkIds": ["net-infra"], "portFilter": None}
            assert payload["destinationFilter"] == {
                "type": "IP_ADDRESSES_OR_SUBNETS",
                "ipAddressesOrSubnets": ["10.0.1.193"],
                "portFilter": [8123],
            }
            assert payload["protocolFilter"] == ["TCP"]


@pytest.mark.asyncio
async def test_create_acl_rule_ambiguous_filter_rejected(mock_settings):
    with pytest.raises(ValueError, match="ambiguous"):
        await create_acl_rule(
            "default",
            "Bad Rule",
            "allow",
            mock_settings,
            source_network_ids=["net-1"],
            source_ports=[443],
            confirm=True,
        )


@pytest.mark.asyncio
async def test_create_acl_rule_mac_requires_network_id_filter(mock_settings):
    with pytest.raises(ValueError, match="network_id_filter is required"):
        await create_acl_rule(
            "default",
            "MAC Rule",
            "allow",
            mock_settings,
            type="MAC",
            confirm=True,
        )


@pytest.mark.asyncio
async def test_create_acl_rule_dry_run(mock_settings):
    with patch("src.tools.acls.UniFiClient") as mock_client_class:
        mock_client = _prepare_client(AsyncMock())
        mock_client.is_authenticated = True
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await create_acl_rule(
            "default",
            "Test Rule",
            "BLOCK",
            mock_settings,
            destination_ip_addresses_or_subnets=["192.168.1.0/24"],
            confirm=True,
            dry_run=True,
        )

        assert result["dry_run"] is True
        assert result["payload"]["name"] == "Test Rule"
        assert result["payload"]["action"] == "BLOCK"
        assert result["payload"]["type"] == "IPV4"
        assert result["payload"]["enabled"] is True
        assert result["payload"]["destinationFilter"] == {
            "type": "IP_ADDRESSES_OR_SUBNETS",
            "ipAddressesOrSubnets": ["192.168.1.0/24"],
            "portFilter": None,
        }
        mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_create_acl_rule_no_confirm(mock_settings):
    with pytest.raises(ValidationError) as excinfo:
        await create_acl_rule(
            "default",
            "Test Rule",
            "deny",
            mock_settings,
            confirm=False,
        )
    assert "requires confirmation" in str(excinfo.value)


@pytest.mark.asyncio
async def test_update_acl_rule_success(mock_settings):
    mock_response = {"data": _ip_rule(name="Updated Rule", enabled=False, action="BLOCK")}

    with patch("src.tools.acls.UniFiClient") as mock_client_class:
        with patch("src.tools.acls.audit_action", new_callable=AsyncMock):
            mock_client = AsyncMock()
            mock_client.is_authenticated = True
            mock_client.put = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await update_acl_rule(
                "default",
                "acl-1",
                mock_settings,
                name="Updated Rule",
                enabled=False,
                confirm=True,
            )

            assert result["name"] == "Updated Rule"
            assert result["enabled"] is False
            mock_client.put.assert_called_once()


@pytest.mark.asyncio
async def test_update_acl_rule_with_filter_requires_type(mock_settings):
    with pytest.raises(ValueError, match="type must be given"):
        await update_acl_rule(
            "default",
            "acl-1",
            mock_settings,
            destination_ip_addresses_or_subnets=["10.0.1.193"],
            confirm=True,
        )


@pytest.mark.asyncio
async def test_update_acl_rule_dry_run(mock_settings):
    with patch("src.tools.acls.UniFiClient") as mock_client_class:
        mock_client = _prepare_client(AsyncMock())
        mock_client.is_authenticated = True
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await update_acl_rule(
            "default",
            "acl-1",
            mock_settings,
            name="Preview Name",
            action="allow",
            confirm=True,
            dry_run=True,
        )

        assert result["dry_run"] is True
        assert result["payload"]["name"] == "Preview Name"
        assert result["payload"]["action"] == "ALLOW"
        mock_client.put.assert_not_called()


@pytest.mark.asyncio
async def test_update_acl_rule_no_confirm(mock_settings):
    with pytest.raises(ValidationError) as excinfo:
        await update_acl_rule(
            "default",
            "acl-1",
            mock_settings,
            name="New Name",
            confirm=False,
        )
    assert "requires confirmation" in str(excinfo.value)


@pytest.mark.asyncio
async def test_update_acl_rule_partial_fields(mock_settings):
    mock_response = {"data": _ip_rule(name="Existing Name", enabled=False, action="BLOCK")}

    with patch("src.tools.acls.UniFiClient") as mock_client_class:
        with patch("src.tools.acls.audit_action", new_callable=AsyncMock):
            mock_client = _prepare_client(AsyncMock())
            mock_client.is_authenticated = True
            mock_client.put = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await update_acl_rule(
                "default",
                "acl-1",
                mock_settings,
                enabled=False,
                confirm=True,
            )

            assert result["enabled"] is False
            call_args = mock_client.put.call_args
            payload = call_args[1]["json_data"]
            assert payload == {"enabled": False}


@pytest.mark.asyncio
async def test_delete_acl_rule_success(mock_settings):
    with patch("src.tools.acls.UniFiClient") as mock_client_class:
        with patch("src.tools.acls.audit_action", new_callable=AsyncMock):
            mock_client = _prepare_client(AsyncMock())
            mock_client.is_authenticated = False
            mock_client.authenticate = AsyncMock()
            mock_client.delete = AsyncMock(return_value={})
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await delete_acl_rule(
                "default",
                "acl-1",
                mock_settings,
                confirm=True,
            )

            assert result["success"] is True
            assert "acl-1" in result["message"]
            mock_client.delete.assert_called_once_with(
                "/integration/v1/sites/default/acl-rules/acl-1"
            )


@pytest.mark.asyncio
async def test_delete_acl_rule_dry_run(mock_settings):
    with patch("src.tools.acls.UniFiClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.is_authenticated = True
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await delete_acl_rule(
            "default",
            "acl-1",
            mock_settings,
            confirm=True,
            dry_run=True,
        )

        assert result["dry_run"] is True
        assert result["acl_rule_id"] == "acl-1"
        mock_client.delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_acl_rule_no_confirm(mock_settings):
    with pytest.raises(ValidationError) as excinfo:
        await delete_acl_rule(
            "default",
            "acl-1",
            mock_settings,
            confirm=False,
        )
    assert "requires confirmation" in str(excinfo.value)
