"""Tests for traffic route tools.

Note: Tests for QoS Profile (5 tools), ProAV Profile (3 tools), and Smart
Queue (3 tools) were removed along with the tools themselves. Those tools
used non-existent API endpoints (rest/qosprofile, rest/wanconf).
See src/tools/qos.py docstring for details.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_settings():
    from src.config import APIType

    settings = MagicMock(spec="Settings")
    settings.log_level = "INFO"
    settings.api_type = APIType.LOCAL
    settings.base_url = "https://192.168.2.1"
    settings.api_key = "test-key"
    settings.local_host = "192.168.2.1"
    settings.local_port = 443
    settings.local_verify_ssl = False
    return settings


@pytest.fixture
def sample_traffic_routes():
    return [
        {
            "_id": "route-001",
            "name": "Block External DNS",
            "description": "Block external DNS queries",
            "action": "deny",
            "enabled": True,
            "match_criteria": {
                "destination_port": 53,
                "protocol": "udp",
            },
            "priority": 100,
            "site_id": "default",
        },
        {
            "_id": "route-002",
            "name": "Prioritize VoIP",
            "description": "Mark VoIP with EF",
            "action": "mark",
            "enabled": True,
            "match_criteria": {
                "destination_port": 5060,
                "protocol": "udp",
            },
            "dscp_marking": 46,
            "priority": 50,
            "site_id": "default",
        },
    ]


class TestListTrafficRoutes:
    @pytest.mark.asyncio
    async def test_list_traffic_routes_success(self, mock_settings, sample_traffic_routes):
        from src.tools.qos import list_traffic_routes

        with patch("src.tools.qos.UniFiClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.is_authenticated = False
            mock_instance.authenticate = AsyncMock()
            mock_instance.resolve_site_id = AsyncMock(return_value="default")
            mock_instance.get = AsyncMock(return_value={"data": sample_traffic_routes})

            result = await list_traffic_routes("default", mock_settings)

            assert len(result) == 2
            assert result[0]["name"] == "Block External DNS"
            assert result[1]["name"] == "Prioritize VoIP"

    @pytest.mark.asyncio
    async def test_list_traffic_routes_pagination(self, mock_settings, sample_traffic_routes):
        from src.tools.qos import list_traffic_routes

        with patch("src.tools.qos.UniFiClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.is_authenticated = False
            mock_instance.authenticate = AsyncMock()
            mock_instance.resolve_site_id = AsyncMock(return_value="default")
            mock_instance.get = AsyncMock(
                return_value={"data": sample_traffic_routes * 3}  # 6 routes
            )

            result = await list_traffic_routes("default", mock_settings, limit=2, offset=2)
            assert len(result) == 2


class TestCreateTrafficRoute:
    @pytest.mark.asyncio
    async def test_create_traffic_route_success(self, mock_settings):
        from src.tools.qos import create_traffic_route

        with patch("src.tools.qos.UniFiClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.is_authenticated = False
            mock_instance.authenticate = AsyncMock()
            mock_instance.resolve_site_id = AsyncMock(return_value="default")
            mock_instance.post = AsyncMock(
                return_value={
                    "data": [
                        {
                            "_id": "route-new",
                            "name": "Test Route",
                            "action": "allow",
                            "enabled": True,
                            "match_criteria": {
                                "destination_port": 443,
                                "protocol": "tcp",
                            },
                            "priority": 100,
                            "site_id": "default",
                        }
                    ]
                }
            )

            with patch("src.tools.qos.audit_action", new_callable=AsyncMock):
                result = await create_traffic_route(
                    site_id="default",
                    name="Test Route",
                    action="allow",
                    settings=mock_settings,
                    destination_port=443,
                    protocol="tcp",
                    confirm=True,
                )

            assert result["name"] == "Test Route"
            assert result["action"] == "allow"

    @pytest.mark.asyncio
    async def test_create_traffic_route_requires_confirmation(self, mock_settings):
        from src.tools.qos import create_traffic_route
        from src.utils.exceptions import ValidationError

        with pytest.raises(ValidationError, match="requires confirmation"):
            await create_traffic_route(
                site_id="default",
                name="Test",
                action="allow",
                settings=mock_settings,
                confirm=False,
            )

    @pytest.mark.asyncio
    async def test_create_traffic_route_invalid_action(self, mock_settings):
        from src.tools.qos import create_traffic_route
        from src.utils.exceptions import ValidationError

        with pytest.raises(ValidationError, match="Invalid action"):
            await create_traffic_route(
                site_id="default",
                name="Test",
                action="invalid",
                settings=mock_settings,
                confirm=True,
            )

    @pytest.mark.asyncio
    async def test_create_traffic_route_invalid_dscp(self, mock_settings):
        from src.tools.qos import create_traffic_route
        from src.utils.exceptions import ValidationError

        with pytest.raises(ValidationError, match="DSCP marking must be 0-63"):
            await create_traffic_route(
                site_id="default",
                name="Test",
                action="mark",
                settings=mock_settings,
                dscp_marking=100,  # Invalid
                confirm=True,
            )

    @pytest.mark.asyncio
    async def test_create_traffic_route_invalid_priority(self, mock_settings):
        from src.tools.qos import create_traffic_route
        from src.utils.exceptions import ValidationError

        with pytest.raises(ValidationError, match="Priority must be 1-1000"):
            await create_traffic_route(
                site_id="default",
                name="Test",
                action="allow",
                settings=mock_settings,
                priority=2000,  # Invalid
                confirm=True,
            )


class TestUpdateTrafficRoute:
    @pytest.mark.asyncio
    async def test_update_traffic_route_success(self, mock_settings, sample_traffic_routes):
        from src.tools.qos import update_traffic_route

        with patch("src.tools.qos.UniFiClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.is_authenticated = False
            mock_instance.authenticate = AsyncMock()
            mock_instance.resolve_site_id = AsyncMock(return_value="default")
            updated_route = sample_traffic_routes[0].copy()
            updated_route["enabled"] = False
            mock_instance.put = AsyncMock(return_value={"data": [updated_route]})

            with patch("src.tools.qos.audit_action", new_callable=AsyncMock):
                result = await update_traffic_route(
                    site_id="default",
                    route_id="route-001",
                    settings=mock_settings,
                    enabled=False,
                    confirm=True,
                )

            assert result["enabled"] is False

    @pytest.mark.asyncio
    async def test_update_traffic_route_requires_confirmation(self, mock_settings):
        from src.tools.qos import update_traffic_route
        from src.utils.exceptions import ValidationError

        with pytest.raises(ValidationError, match="requires confirmation"):
            await update_traffic_route(
                site_id="default",
                route_id="route-001",
                settings=mock_settings,
                enabled=False,
                confirm=False,
            )

    @pytest.mark.asyncio
    async def test_update_traffic_route_no_fields(self, mock_settings):
        from src.tools.qos import update_traffic_route
        from src.utils.exceptions import ValidationError

        with pytest.raises(ValidationError, match="No update fields provided"):
            await update_traffic_route(
                site_id="default",
                route_id="route-001",
                settings=mock_settings,
                confirm=True,
            )


class TestDeleteTrafficRoute:
    @pytest.mark.asyncio
    async def test_delete_traffic_route_success(self, mock_settings):
        from src.tools.qos import delete_traffic_route

        with patch("src.tools.qos.UniFiClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.is_authenticated = False
            mock_instance.authenticate = AsyncMock()
            mock_instance.resolve_site_id = AsyncMock(return_value="default")
            mock_instance.delete = AsyncMock(return_value={})

            with patch("src.tools.qos.audit_action", new_callable=AsyncMock):
                result = await delete_traffic_route(
                    site_id="default",
                    route_id="route-001",
                    settings=mock_settings,
                    confirm=True,
                )

            assert result["success"] is True
            assert result["route_id"] == "route-001"

    @pytest.mark.asyncio
    async def test_delete_traffic_route_requires_confirmation(self, mock_settings):
        from src.tools.qos import delete_traffic_route
        from src.utils.exceptions import ValidationError

        with pytest.raises(ValidationError, match="requires confirmation"):
            await delete_traffic_route(
                site_id="default",
                route_id="route-001",
                settings=mock_settings,
                confirm=False,
            )
