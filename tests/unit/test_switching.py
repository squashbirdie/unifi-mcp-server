"""Unit tests for src/tools/switching.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.utils.exceptions import ResourceNotFoundError, ValidationError


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.log_level = "INFO"
    settings.get_integration_path = MagicMock(side_effect=lambda x: f"/integration/v1/{x}")
    return settings


def make_switch_stack(stack_id="ss-123", name="Core Stack"):
    return {
        "id": stack_id,
        "name": name,
        "members": [{"deviceId": "dev-1"}, {"deviceId": "dev-2"}],
        "lags": [],
        "metadata": {"origin": "user"},
    }


def make_mclag_domain(domain_id="mc-123", name="Core Domain"):
    return {
        "id": domain_id,
        "name": name,
        "peers": [{"deviceId": "dev-1"}],
        "lags": [],
        "metadata": {"origin": "user"},
    }


def make_lag(lag_id="lag-123", lag_type="SWITCH_STACK", switch_stack_id="ss-123"):
    return {
        "type": lag_type,
        "id": lag_id,
        "members": [{"deviceId": "dev-1", "portIdxs": [1, 2]}],
        "switchStackId": switch_stack_id,
    }


class TestListSwitchStacks:
    @pytest.mark.asyncio
    async def test_list_switch_stacks_success(self, mock_settings):
        from src.tools.switching import list_switch_stacks

        response = {"data": [make_switch_stack("ss-1"), make_switch_stack("ss-2")]}

        with patch("src.tools.switching.UniFiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.authenticate = AsyncMock()
            mock_client.get = AsyncMock(return_value=response)

            result = await list_switch_stacks("site-1", mock_settings)

            assert len(result) == 2
            assert result[0]["id"] == "ss-1"
            assert result[1]["id"] == "ss-2"

    @pytest.mark.asyncio
    async def test_list_switch_stacks_empty(self, mock_settings):
        from src.tools.switching import list_switch_stacks

        with patch("src.tools.switching.UniFiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.authenticate = AsyncMock()
            mock_client.get = AsyncMock(return_value={"data": []})

            result = await list_switch_stacks("site-1", mock_settings)

            assert result == []

    @pytest.mark.asyncio
    async def test_list_switch_stacks_invalid_site_id(self, mock_settings):
        from src.tools.switching import list_switch_stacks

        with pytest.raises(ValidationError):
            await list_switch_stacks("", mock_settings)


class TestGetSwitchStack:
    @pytest.mark.asyncio
    async def test_get_switch_stack_success(self, mock_settings):
        from src.tools.switching import get_switch_stack

        stack_id = "ss-123"
        response = {"data": [make_switch_stack(stack_id, "Core Stack")]}

        with patch("src.tools.switching.UniFiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.authenticate = AsyncMock()
            mock_client.get = AsyncMock(return_value=response)

            result = await get_switch_stack("site-1", stack_id, mock_settings)

            assert result["id"] == stack_id
            assert result["name"] == "Core Stack"

    @pytest.mark.asyncio
    async def test_get_switch_stack_not_found(self, mock_settings):
        from src.tools.switching import get_switch_stack

        with patch("src.tools.switching.UniFiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.authenticate = AsyncMock()
            mock_client.get = AsyncMock(return_value={"data": []})

            with pytest.raises(ResourceNotFoundError):
                await get_switch_stack("site-1", "missing-id", mock_settings)

    @pytest.mark.asyncio
    async def test_get_switch_stack_invalid_site_id(self, mock_settings):
        from src.tools.switching import get_switch_stack

        with pytest.raises(ValidationError):
            await get_switch_stack("", "ss-123", mock_settings)


class TestListMclagDomains:
    @pytest.mark.asyncio
    async def test_list_mclag_domains_success(self, mock_settings):
        from src.tools.switching import list_mclag_domains

        response = {"data": [make_mclag_domain("mc-1"), make_mclag_domain("mc-2")]}

        with patch("src.tools.switching.UniFiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.authenticate = AsyncMock()
            mock_client.get = AsyncMock(return_value=response)

            result = await list_mclag_domains("site-1", mock_settings)

            assert len(result) == 2
            assert result[0]["id"] == "mc-1"
            assert result[1]["id"] == "mc-2"

    @pytest.mark.asyncio
    async def test_list_mclag_domains_empty(self, mock_settings):
        from src.tools.switching import list_mclag_domains

        with patch("src.tools.switching.UniFiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.authenticate = AsyncMock()
            mock_client.get = AsyncMock(return_value={"data": []})

            result = await list_mclag_domains("site-1", mock_settings)

            assert result == []

    @pytest.mark.asyncio
    async def test_list_mclag_domains_invalid_site_id(self, mock_settings):
        from src.tools.switching import list_mclag_domains

        with pytest.raises(ValidationError):
            await list_mclag_domains("", mock_settings)


class TestGetMclagDomain:
    @pytest.mark.asyncio
    async def test_get_mclag_domain_success(self, mock_settings):
        from src.tools.switching import get_mclag_domain

        domain_id = "mc-123"
        response = {"data": [make_mclag_domain(domain_id, "Core Domain")]}

        with patch("src.tools.switching.UniFiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.authenticate = AsyncMock()
            mock_client.get = AsyncMock(return_value=response)

            result = await get_mclag_domain("site-1", domain_id, mock_settings)

            assert result["id"] == domain_id
            assert result["name"] == "Core Domain"

    @pytest.mark.asyncio
    async def test_get_mclag_domain_not_found(self, mock_settings):
        from src.tools.switching import get_mclag_domain

        with patch("src.tools.switching.UniFiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.authenticate = AsyncMock()
            mock_client.get = AsyncMock(return_value={"data": []})

            with pytest.raises(ResourceNotFoundError):
                await get_mclag_domain("site-1", "missing-id", mock_settings)

    @pytest.mark.asyncio
    async def test_get_mclag_domain_invalid_site_id(self, mock_settings):
        from src.tools.switching import get_mclag_domain

        with pytest.raises(ValidationError):
            await get_mclag_domain("", "mc-123", mock_settings)


class TestListLags:
    @pytest.mark.asyncio
    async def test_list_lags_success(self, mock_settings):
        from src.tools.switching import list_lags

        response = {"data": [make_lag("lag-1"), make_lag("lag-2", "MULTI_CHASSIS")]}

        with patch("src.tools.switching.UniFiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.authenticate = AsyncMock()
            mock_client.get = AsyncMock(return_value=response)

            result = await list_lags("site-1", mock_settings)

            assert len(result) == 2
            assert result[0]["id"] == "lag-1"
            assert result[1]["type"] == "MULTI_CHASSIS"

    @pytest.mark.asyncio
    async def test_list_lags_empty(self, mock_settings):
        from src.tools.switching import list_lags

        with patch("src.tools.switching.UniFiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.authenticate = AsyncMock()
            mock_client.get = AsyncMock(return_value={"data": []})

            result = await list_lags("site-1", mock_settings)

            assert result == []

    @pytest.mark.asyncio
    async def test_list_lags_invalid_site_id(self, mock_settings):
        from src.tools.switching import list_lags

        with pytest.raises(ValidationError):
            await list_lags("", mock_settings)


class TestGetLagDetails:
    @pytest.mark.asyncio
    async def test_get_lag_details_success(self, mock_settings):
        from src.tools.switching import get_lag_details

        lag_id = "lag-123"
        response = {"data": [make_lag(lag_id, "LOCAL")]}

        with patch("src.tools.switching.UniFiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.authenticate = AsyncMock()
            mock_client.get = AsyncMock(return_value=response)

            result = await get_lag_details("site-1", lag_id, mock_settings)

            assert result["id"] == lag_id
            assert result["type"] == "LOCAL"
            assert result["switch_stack_id"] == "ss-123"
            assert len(result["members"]) == 1
            assert result["members"][0]["device_id"] == "dev-1"
            assert result["members"][0]["port_idxs"] == [1, 2]

    @pytest.mark.asyncio
    async def test_get_lag_details_not_found(self, mock_settings):
        from src.tools.switching import get_lag_details

        with patch("src.tools.switching.UniFiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.authenticate = AsyncMock()
            mock_client.get = AsyncMock(return_value={"data": []})

            with pytest.raises(ResourceNotFoundError):
                await get_lag_details("site-1", "missing-id", mock_settings)

    @pytest.mark.asyncio
    async def test_get_lag_details_invalid_site_id(self, mock_settings):
        from src.tools.switching import get_lag_details

        with pytest.raises(ValidationError):
            await get_lag_details("", "lag-123", mock_settings)

    @pytest.mark.asyncio
    async def test_get_lag_details_empty_lag_id(self, mock_settings):
        from src.tools.switching import get_lag_details

        with pytest.raises(ValidationError):
            await get_lag_details("site-1", "", mock_settings)
