"""Unit tests for UniFi API client."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.api.client import RateLimiter, UniFiClient
from src.config import APIType
from src.utils.exceptions import (
    APIError,
    AuthenticationError,
    NetworkError,
    RateLimitError,
    ResourceNotFoundError,
)


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.log_level = "INFO"
    settings.api_type = APIType.CLOUD_EA
    settings.base_url = "https://api.ui.com"
    settings.api_key = "test-api-key"
    settings.request_timeout = 30.0
    settings.verify_ssl = True
    settings.rate_limit_requests = 100
    settings.rate_limit_period = 60
    settings.max_retries = 3
    settings.retry_backoff_factor = 2
    settings.retry_total_timeout = 60
    settings.log_api_requests = True
    settings.default_site = "default"
    settings.get_headers = MagicMock(return_value={"X-API-Key": "test-api-key"})
    return settings


@pytest.fixture
def mock_settings_local():
    settings = MagicMock()
    settings.log_level = "INFO"
    settings.api_type = APIType.LOCAL
    settings.base_url = "https://192.168.2.1"
    settings.api_key = "test-api-key"
    settings.request_timeout = 30.0
    settings.verify_ssl = False
    settings.rate_limit_requests = 100
    settings.rate_limit_period = 60
    settings.max_retries = 3
    settings.retry_backoff_factor = 2
    settings.retry_total_timeout = 60
    settings.log_api_requests = True
    settings.default_site = "default"
    settings.get_headers = MagicMock(return_value={"X-API-Key": "test-api-key"})
    return settings


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_acquire_within_limit(self):
        limiter = RateLimiter(requests_per_period=10, period_seconds=60)

        for _ in range(5):
            await limiter.acquire()

        assert limiter.tokens >= 4

    @pytest.mark.asyncio
    async def test_acquire_depletes_tokens(self):
        limiter = RateLimiter(requests_per_period=5, period_seconds=60)
        initial_tokens = limiter.tokens

        await limiter.acquire()
        assert limiter.tokens < initial_tokens

        await limiter.acquire()
        assert limiter.tokens < initial_tokens - 1

    @pytest.mark.asyncio
    async def test_acquire_waits_when_exhausted(self):
        limiter = RateLimiter(requests_per_period=100, period_seconds=1)
        limiter.tokens = 0.0

        start = asyncio.get_event_loop().time()
        await limiter.acquire()
        duration = asyncio.get_event_loop().time() - start

        assert duration >= 0.001


class TestUniFiClientInit:
    @pytest.mark.asyncio
    async def test_client_init(self, mock_settings):
        client = UniFiClient(mock_settings)

        assert client.settings == mock_settings
        assert client._authenticated is False
        assert client._site_id_cache == {}
        await client.close()

    @pytest.mark.asyncio
    async def test_client_context_manager(self, mock_settings):
        async with UniFiClient(mock_settings) as client:
            assert client is not None
            assert isinstance(client, UniFiClient)

    @pytest.mark.asyncio
    async def test_is_authenticated_property(self, mock_settings):
        client = UniFiClient(mock_settings)

        assert client.is_authenticated is False
        client._authenticated = True
        assert client.is_authenticated is True

        await client.close()


class TestUniFiClientEndpointTranslation:
    @pytest.mark.asyncio
    async def test_translate_cloud_ea_unchanged(self, mock_settings):
        client = UniFiClient(mock_settings)

        result = client._translate_endpoint("/ea/sites")
        assert result == "/ea/sites"

        result = client._translate_endpoint("/ea/sites/default/devices")
        assert result == "/ea/sites/default/devices"

        await client.close()

    @pytest.mark.asyncio
    async def test_translate_cloud_v1_unchanged(self, mock_settings):
        mock_settings.api_type = APIType.CLOUD_V1
        client = UniFiClient(mock_settings)

        result = client._translate_endpoint("/v1/hosts")
        assert result == "/v1/hosts"

        await client.close()

    @pytest.mark.asyncio
    async def test_translate_local_sites(self, mock_settings_local):
        client = UniFiClient(mock_settings_local)

        result = client._translate_endpoint("/ea/sites")
        assert result == "/proxy/network/integration/v1/sites"

        await client.close()

    @pytest.mark.asyncio
    async def test_translate_local_devices(self, mock_settings_local):
        client = UniFiClient(mock_settings_local)

        result = client._translate_endpoint("/ea/sites/default/devices")
        assert result == "/proxy/network/api/s/default/stat/device"

        await client.close()

    @pytest.mark.asyncio
    async def test_translate_local_with_uuid_mapping(self, mock_settings_local):
        client = UniFiClient(mock_settings_local)
        client._site_uuid_to_name = {"abc-123-uuid": "default"}

        result = client._translate_endpoint("/ea/sites/abc-123-uuid/devices")
        assert result == "/proxy/network/api/s/default/stat/device"

        await client.close()

    @pytest.mark.asyncio
    async def test_translate_local_site_detail(self, mock_settings_local):
        client = UniFiClient(mock_settings_local)

        result = client._translate_endpoint("/ea/sites/default")
        assert result == "/proxy/network/api/s/default/self"

        await client.close()

    @pytest.mark.asyncio
    async def test_translate_local_v2_api_uuid_resolved(self, mock_settings_local):
        """v2 API paths (built by Settings.get_v2_api_path) embed a site UUID
        just like the /ea/sites/ pattern, and need the same resolution."""
        client = UniFiClient(mock_settings_local)
        client._site_uuid_to_name = {"abc-123-uuid": "default"}

        result = client._translate_endpoint(
            "/proxy/network/v2/api/site/abc-123-uuid/firewall-policies"
        )
        assert result == "/proxy/network/v2/api/site/default/firewall-policies"

        await client.close()

    @pytest.mark.asyncio
    async def test_translate_local_v2_api_uuid_unmapped_passthrough(self, mock_settings_local):
        """Without a mapping, the original id is kept rather than dropped."""
        client = UniFiClient(mock_settings_local)

        result = client._translate_endpoint("/proxy/network/v2/api/site/default/firewall-policies")
        assert result == "/proxy/network/v2/api/site/default/firewall-policies"

        await client.close()

    @pytest.mark.asyncio
    async def test_translate_local_rest_api_s_uuid_resolved(self, mock_settings_local):
        """Callers that build /proxy/network/api/s/{id}/... directly (e.g.
        site_vpn.py) get the same UUID -> internalReference resolution as
        the /ea/sites/ pattern, instead of silently sending a UUID the
        local controller rejects with api.err.NoSiteContext."""
        client = UniFiClient(mock_settings_local)
        client._site_uuid_to_name = {"abc-123-uuid": "default"}

        result = client._translate_endpoint("/proxy/network/api/s/abc-123-uuid/rest/networkconf")
        assert result == "/proxy/network/api/s/default/rest/networkconf"

        await client.close()


class TestUniFiClientEnsureSiteMap:
    """Regression coverage for the lazy site-map resolution bug: most tool
    functions never called authenticate() before making their real request,
    so _site_uuid_to_name stayed empty and every /ea/sites/{uuid}/... or v2
    API call sent the UUID straight through, failing with
    api.err.NoSiteContext on a real controller."""

    @pytest.mark.asyncio
    async def test_ensure_site_map_populates_lazily(self, mock_settings_local):
        client = UniFiClient(mock_settings_local)
        assert client._site_uuid_to_name == {}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '[{"id": "uuid-1", "internalReference": "default"}]'
        mock_response.json = MagicMock(
            return_value=[{"id": "uuid-1", "internalReference": "default"}]
        )

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            # No explicit authenticate() call here — this is the exact gap
            # that left ~25 read-only tools broken.
            await client._ensure_site_map()

        assert client._site_uuid_to_name == {"uuid-1": "default"}
        await client.close()

    @pytest.mark.asyncio
    async def test_ensure_site_map_skips_when_already_populated(self, mock_settings_local):
        client = UniFiClient(mock_settings_local)
        client._site_uuid_to_name = {"uuid-1": "default"}

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            await client._ensure_site_map()
            mock_request.assert_not_called()

        await client.close()

    @pytest.mark.asyncio
    async def test_ensure_site_map_skips_for_cloud(self, mock_settings):
        client = UniFiClient(mock_settings)  # cloud-ea, not local

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            await client._ensure_site_map()
            mock_request.assert_not_called()

        await client.close()

    @pytest.mark.asyncio
    async def test_ensure_site_map_shared_across_instances(self, mock_settings_local):
        """A second client against the same controller must not re-fetch —
        the whole point of promoting the cache to class level."""
        first = UniFiClient(mock_settings_local)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '[{"id": "uuid-1", "internalReference": "default"}]'
        mock_response.json = MagicMock(
            return_value=[{"id": "uuid-1", "internalReference": "default"}]
        )
        with patch.object(first.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            await first._ensure_site_map()
        await first.close()

        second = UniFiClient(mock_settings_local)
        assert second._site_uuid_to_name == {"uuid-1": "default"}
        with patch.object(second.client, "request", new_callable=AsyncMock) as mock_request:
            await second._ensure_site_map()
            mock_request.assert_not_called()
        await second.close()

    @pytest.mark.asyncio
    async def test_request_triggers_ensure_site_map_before_translation(self, mock_settings_local):
        """End-to-end: a plain client.get() call for a UUID-scoped endpoint,
        with no prior authenticate(), still resolves the site name — this is
        the exact call shape every broken tool function used."""
        client = UniFiClient(mock_settings_local)

        sites_response = MagicMock()
        sites_response.status_code = 200
        sites_response.text = '[{"id": "abc-123-uuid", "internalReference": "default"}]'
        sites_response.json = MagicMock(
            return_value=[{"id": "abc-123-uuid", "internalReference": "default"}]
        )
        devices_response = MagicMock()
        devices_response.status_code = 200
        devices_response.text = "[]"
        devices_response.json = MagicMock(return_value=[])

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = [sites_response, devices_response]
            await client.get("/ea/sites/abc-123-uuid/devices")

            assert mock_request.call_count == 2
            first_call_url = mock_request.call_args_list[0].kwargs["url"]
            second_call_url = mock_request.call_args_list[1].kwargs["url"]
            assert first_call_url.endswith("/proxy/network/integration/v1/sites")
            assert second_call_url.endswith("/proxy/network/api/s/default/stat/device")

        await client.close()


class TestUniFiClientAuthentication:
    @pytest.mark.asyncio
    async def test_authenticate_success_list_response(self, mock_settings):
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '[{"id": "site1"}]'
        mock_response.json = MagicMock(return_value=[{"id": "site1"}])

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            await client.authenticate()

        assert client._authenticated is True
        await client.close()

    @pytest.mark.asyncio
    async def test_authenticate_success_dict_response(self, mock_settings):
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"data": [{"id": "site1"}]}'
        mock_response.json = MagicMock(return_value={"data": [{"id": "site1"}]})

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            await client.authenticate()

        assert client._authenticated is True
        await client.close()

    @pytest.mark.asyncio
    async def test_authenticate_failure(self, mock_settings):
        client = UniFiClient(mock_settings)

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = Exception("Connection refused")

            with pytest.raises(AuthenticationError, match="Failed to authenticate"):
                await client.authenticate()

        await client.close()

    @pytest.mark.asyncio
    async def test_build_site_uuid_map(self, mock_settings_local):
        client = UniFiClient(mock_settings_local)

        sites = [
            {"id": "uuid-1", "internalReference": "default"},
            {"id": "uuid-2", "internalReference": "office"},
        ]

        client._build_site_uuid_map(sites)

        assert client._site_uuid_to_name["uuid-1"] == "default"
        assert client._site_uuid_to_name["uuid-2"] == "office"
        await client.close()


class TestUniFiClientHttpMethods:
    @pytest.mark.asyncio
    async def test_get_success(self, mock_settings):
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"data": [{"id": "device1"}]}'
        mock_response.json = MagicMock(return_value={"data": [{"id": "device1"}]})

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            result = await client.get("/ea/sites/default/devices")

        assert result == {"data": [{"id": "device1"}]}
        await client.close()

    @pytest.mark.asyncio
    async def test_post_success(self, mock_settings):
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"data": {"id": "new-resource"}}'
        mock_response.json = MagicMock(return_value={"data": {"id": "new-resource"}})

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            result = await client.post("/ea/sites/default/networks", {"name": "test"})

        assert result == {"data": {"id": "new-resource"}}
        await client.close()

    @pytest.mark.asyncio
    async def test_put_success(self, mock_settings):
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"data": {"id": "updated"}}'
        mock_response.json = MagicMock(return_value={"data": {"id": "updated"}})

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            result = await client.put("/ea/sites/default/networks/123", {"name": "updated"})

        assert result == {"data": {"id": "updated"}}
        await client.close()

    @pytest.mark.asyncio
    async def test_delete_success(self, mock_settings):
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "{}"
        mock_response.json = MagicMock(return_value={})

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            result = await client.delete("/ea/sites/default/networks/123")

        assert result == {}
        await client.close()


class TestUniFiClientErrorHandling:
    @pytest.mark.asyncio
    async def test_rate_limit_error(self, mock_settings):
        mock_settings.max_retries = 0
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "30"}

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            with pytest.raises(RateLimitError):
                await client.get("/ea/sites")

        await client.close()

    @pytest.mark.asyncio
    async def test_not_found_error(self, mock_settings):
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            with pytest.raises(ResourceNotFoundError):
                await client.get("/ea/sites/nonexistent")

        await client.close()

    @pytest.mark.asyncio
    async def test_authentication_error_401(self, mock_settings):
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            with pytest.raises(AuthenticationError, match="Authentication failed"):
                await client.get("/ea/sites")

        await client.close()

    @pytest.mark.asyncio
    async def test_authentication_error_403(self, mock_settings):
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            with pytest.raises(AuthenticationError, match="Authentication failed"):
                await client.get("/ea/sites")

        await client.close()

    @pytest.mark.asyncio
    async def test_api_error(self, mock_settings):
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.json = MagicMock(return_value={"error": "Server error"})

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            with pytest.raises(APIError, match="API request failed"):
                await client.get("/ea/sites")

        await client.close()

    @pytest.mark.asyncio
    async def test_timeout_retry(self, mock_settings):
        mock_settings.max_retries = 2
        mock_settings.retry_backoff_factor = 0.01
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"data": []}'
        mock_response.json = MagicMock(return_value={"data": []})

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.TimeoutException("timeout")
            return mock_response

        with patch.object(client.client, "request", side_effect=side_effect):
            result = await client.get("/ea/sites")

        assert result == {"data": []}
        assert call_count == 2
        await client.close()

    @pytest.mark.asyncio
    async def test_timeout_max_retries_exceeded(self, mock_settings):
        mock_settings.max_retries = 1
        mock_settings.retry_backoff_factor = 0.01
        client = UniFiClient(mock_settings)

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = httpx.TimeoutException("timeout")

            with pytest.raises(NetworkError, match="timeout"):
                await client.get("/ea/sites")

        await client.close()

    @pytest.mark.asyncio
    async def test_retry_budget_bounds_wall_clock(self, mock_settings):
        """Retries stop when the time budget is spent, not just at max_retries.

        Regression for #97: with a 30s request timeout, four attempts plus
        backoff legitimately burn ~127s per request, and a tool that
        authenticates first stacks two of those — a four-minute hang from the
        caller's side. The budget converts that into a fast, explained
        failure.
        """
        mock_settings.max_retries = 10
        mock_settings.retry_backoff_factor = 100  # first backoff alone busts the budget
        mock_settings.retry_total_timeout = 5
        client = UniFiClient(mock_settings)

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = httpx.TimeoutException("timeout")

            with pytest.raises(NetworkError, match="retry budget"):
                await client.get("/ea/sites")

        # Attempt 1 fails, backoff 100**0=1s fits the 5s budget, attempt 2
        # fails, backoff 100**1=100s busts it — the check runs BEFORE the
        # sleep, so the test never actually waits.
        assert mock_request.call_count == 2
        await client.close()

    @pytest.mark.asyncio
    async def test_retry_budget_rate_limit_keeps_budget_error(self, mock_settings):
        """A 429 whose Retry-After exceeds the budget fails with the budget message.

        The 429 branch runs inside the request's try block, so without NetworkError
        in the re-raise list the budget error was wrapped as "Unexpected error".
        """
        mock_settings.max_retries = 3
        mock_settings.retry_total_timeout = 5
        client = UniFiClient(mock_settings)

        rate_limited = MagicMock()
        rate_limited.status_code = 429
        rate_limited.headers = {"Retry-After": "60"}

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = rate_limited

            with pytest.raises(NetworkError, match="retry budget"):
                await client.get("/ea/sites")

        assert mock_request.call_count == 1
        await client.close()

    @pytest.mark.asyncio
    async def test_retry_budget_allows_fast_retries(self, mock_settings):
        """Quick retries inside the budget still happen."""
        mock_settings.max_retries = 2
        mock_settings.retry_backoff_factor = 0.01
        mock_settings.retry_total_timeout = 60
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"data": []}'
        mock_response.json = MagicMock(return_value={"data": []})

        calls = 0

        async def side_effect(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls < 3:
                raise httpx.TimeoutException("timeout")
            return mock_response

        with patch.object(client.client, "request", side_effect=side_effect):
            result = await client.get("/ea/sites")

        assert result == {"data": []}
        assert calls == 3
        await client.close()

    @pytest.mark.asyncio
    async def test_network_error_retry(self, mock_settings):
        mock_settings.max_retries = 2
        mock_settings.retry_backoff_factor = 0.01
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"data": []}'
        mock_response.json = MagicMock(return_value={"data": []})

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.NetworkError("connection reset")
            return mock_response

        with patch.object(client.client, "request", side_effect=side_effect):
            result = await client.get("/ea/sites")

        assert result == {"data": []}
        assert call_count == 2
        await client.close()


class TestUniFiClientResponseParsing:
    @pytest.mark.asyncio
    async def test_parse_empty_response(self, mock_settings):
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""
        mock_response.json = MagicMock(return_value={})

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            result = await client.get("/ea/sites/default/some-endpoint")

        assert result == {}
        await client.close()

    @pytest.mark.asyncio
    async def test_parse_invalid_json(self, mock_settings):
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "not json"
        mock_response.json = MagicMock(side_effect=ValueError("Invalid JSON"))

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            result = await client.get("/ea/sites")

        assert result == {}
        await client.close()

    @pytest.mark.asyncio
    async def test_https_force_correction(self, mock_settings):
        mock_settings.base_url = "http://api.ui.com"
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"data": []}'
        mock_response.json = MagicMock(return_value={"data": []})

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            await client.get("/ea/sites")

            call_args = mock_request.call_args
            assert call_args[1]["url"].startswith("https://")

        await client.close()


class TestUniFiClientBackupMethods:
    """Tests for backup-related client methods."""

    @pytest.mark.asyncio
    async def test_get_restore_status_returns_not_supported(self, mock_settings):
        """get_restore_status returns a not_supported status (endpoint not in UniFi API)."""
        client = UniFiClient(mock_settings)
        result = await client.get_restore_status(operation_id="op-123")
        assert result["status"] == "not_supported"
        assert result["operation_id"] == "op-123"
        assert "message" in result
        await client.close()

    @pytest.mark.asyncio
    async def test_configure_backup_schedule_local(self, mock_settings_local):
        """configure_backup_schedule calls PUT on the local endpoint."""
        client = UniFiClient(mock_settings_local)
        client._site_uuid_to_name = {"default": "default"}

        schedule = {"_id": "ab-1", "key": "auto_backup", "auto_backup_enabled": False}
        with patch.object(client, "resolve_site_id", new=AsyncMock(return_value="default")):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = '{"data": [{"_id": "ab-1"}]}'
            mock_response.json = MagicMock(return_value={"data": [schedule]})

            with patch.object(client.client, "request", new_callable=AsyncMock) as mock_req:
                mock_req.return_value = mock_response
                await client.configure_backup_schedule(
                    site_id="default",
                    backup_type="network",
                    frequency="daily",
                    time_of_day="02:00",
                    enabled=True,
                    retention_days=30,
                    max_backups=10,
                )

        # Read of the section, then the settings write onto its _id.
        put_call = mock_req.call_args_list[-1]
        assert "/proxy/network/api/s/default/set/setting/auto_backup/ab-1" in put_call[1]["url"]
        body = put_call[1]["json"]
        assert body["auto_backup_enabled"] is True
        assert body["auto_backup_cron_expr"] == "00 02 * * *"
        assert body["auto_backup_max_files"] == 10
        await client.close()

    @pytest.mark.asyncio
    async def test_configure_backup_schedule_weekly_day_mapping(self, mock_settings_local):
        """Weekly schedules translate 0=Monday..6=Sunday into cron day names.

        Regression: the cron expression used the integer directly, where 0 is
        both falsy (Monday silently became the fallback day) and, in cron's
        own numbering, Sunday.
        """
        client = UniFiClient(mock_settings_local)
        client._site_uuid_to_name = {"default": "default"}

        schedule = {"_id": "ab-1", "key": "auto_backup", "auto_backup_enabled": False}
        for day, expected in [(0, "mon"), (5, "sat"), (6, "sun"), ("Monday", "mon")]:
            with patch.object(client, "resolve_site_id", new=AsyncMock(return_value="default")):
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.text = '{"data": [{"_id": "ab-1"}]}'
                mock_response.json = MagicMock(return_value={"data": [schedule]})

                with patch.object(client.client, "request", new_callable=AsyncMock) as mock_req:
                    mock_req.return_value = mock_response
                    await client.configure_backup_schedule(
                        site_id="default",
                        frequency="weekly",
                        time_of_day="03:30",
                        day_of_week=day,
                    )

            body = mock_req.call_args_list[-1][1]["json"]
            assert body["auto_backup_cron_expr"] == f"30 03 * * {expected}"

        with pytest.raises(APIError, match="day_of_week"):
            await client.configure_backup_schedule(
                site_id="default", frequency="weekly", day_of_week=7
            )
        await client.close()

    @pytest.mark.asyncio
    async def test_get_backup_schedule_reraises_real_errors(self, mock_settings_local):
        """Only not-found style APIErrors mean absence; others must surface."""
        client = UniFiClient(mock_settings_local)
        client._site_uuid_to_name = {"default": "default"}

        with patch.object(client, "resolve_site_id", new=AsyncMock(return_value="default")):
            with patch.object(
                client, "get", new=AsyncMock(side_effect=APIError("api.err.Invalid"))
            ):
                assert await client.get_backup_schedule("default") == {}

            with patch.object(
                client, "get", new=AsyncMock(side_effect=APIError("HTTP 500: server exploded"))
            ):
                with pytest.raises(APIError, match="500"):
                    await client.get_backup_schedule("default")
        await client.close()

    @pytest.mark.asyncio
    async def test_configure_backup_schedule_cloud(self, mock_settings):
        """configure_backup_schedule calls PUT on the cloud endpoint."""
        client = UniFiClient(mock_settings)

        with patch.object(client, "resolve_site_id", new=AsyncMock(return_value="site-uuid")):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = '{"data": []}'
            mock_response.json = MagicMock(return_value={"data": []})

            with patch.object(client.client, "request", new_callable=AsyncMock) as mock_req:
                mock_req.return_value = mock_response
                with pytest.raises(APIError, match="auto_backup"):
                    await client.configure_backup_schedule(
                        site_id="site-uuid",
                        backup_type="network",
                        frequency="weekly",
                        time_of_day="03:00",
                        enabled=True,
                        retention_days=14,
                        max_backups=5,
                        day_of_week="monday",
                    )

        # A controller with no auto_backup section (UniFi OS consoles) is
        # told so; nothing is written.
        assert mock_req.call_count == 1
        await client.close()

    @pytest.mark.asyncio
    async def test_get_backup_schedule_local_returns_dict(self, mock_settings_local):
        """get_backup_schedule returns a dict for a configured schedule."""
        client = UniFiClient(mock_settings_local)
        client._site_uuid_to_name = {"default": "default"}

        with patch.object(client, "resolve_site_id", new=AsyncMock(return_value="default")):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = '{"data": {"schedule_id": "sched-1", "enabled": true}}'
            mock_response.json = MagicMock(
                return_value={"data": {"schedule_id": "sched-1", "enabled": True}}
            )

            with patch.object(client.client, "request", new_callable=AsyncMock) as mock_req:
                mock_req.return_value = mock_response
                result = await client.get_backup_schedule(site_id="default")

        assert isinstance(result, dict)
        await client.close()

    @pytest.mark.asyncio
    async def test_get_backup_schedule_empty_list_returns_empty_dict(self, mock_settings):
        """get_backup_schedule returns empty dict when API returns empty list."""
        client = UniFiClient(mock_settings)

        with patch.object(client, "resolve_site_id", new=AsyncMock(return_value="site-uuid")):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "[]"
            mock_response.json = MagicMock(return_value=[])

            with patch.object(client.client, "request", new_callable=AsyncMock) as mock_req:
                mock_req.return_value = mock_response
                result = await client.get_backup_schedule(site_id="site-uuid")

        assert result == {}
        await client.close()

    @pytest.mark.asyncio
    async def test_get_backup_schedule_super_mgmt_fallback(self, mock_settings_local):
        """UniFi OS consoles: schedule is read from super_mgmt when auto_backup is absent."""
        client = UniFiClient(mock_settings_local)
        client._site_uuid_to_name = {"default": "default"}

        super_mgmt = {
            "_id": "sm-1",
            "autobackup_enabled": True,
            "autobackup_cron_expr": "30 0 1 * *",
            "autobackup_timezone": "America/Denver",
            "autobackup_days": 30,
            "autobackup_max_files": 10,
        }

        with patch.object(client, "resolve_site_id", new=AsyncMock(return_value="default")):
            with patch.object(
                client,
                "get",
                new=AsyncMock(side_effect=[APIError("api.err.Invalid"), {"data": [super_mgmt]}]),
            ) as mock_get:
                result = await client.get_backup_schedule("default")

        assert result == {
            "key": "auto_backup",
            "_id": "sm-1",
            "auto_backup_enabled": True,
            "auto_backup_cron_expr": "30 0 1 * *",
            "auto_backup_timezone": "America/Denver",
            "auto_backup_days": 30,
            "auto_backup_max_files": 10,
        }
        # Two GETs: auto_backup (failed), then super_mgmt
        assert mock_get.await_count == 2
        assert "super_mgmt" in mock_get.await_args_list[1].args[0]
        await client.close()

    @pytest.mark.asyncio
    async def test_get_backup_schedule_super_mgmt_absent(self, mock_settings_local):
        """No autobackup fields in super_mgmt means console-managed; report {}."""
        client = UniFiClient(mock_settings_local)
        client._site_uuid_to_name = {"default": "default"}

        with patch.object(client, "resolve_site_id", new=AsyncMock(return_value="default")):
            with patch.object(
                client,
                "get",
                new=AsyncMock(
                    side_effect=[APIError("api.err.Invalid"), {"data": [{"_id": "sm-1"}]}]
                ),
            ):
                result = await client.get_backup_schedule("default")

        assert result == {}
        await client.close()

    @pytest.mark.asyncio
    async def test_get_backup_schedule_super_mgmt_real_error_reraises(self, mock_settings_local):
        """A real error from the super_mgmt fallback must surface, not be swallowed."""
        client = UniFiClient(mock_settings_local)
        client._site_uuid_to_name = {"default": "default"}

        with patch.object(client, "resolve_site_id", new=AsyncMock(return_value="default")):
            with patch.object(
                client,
                "get",
                new=AsyncMock(
                    side_effect=[APIError("api.err.Invalid"), APIError("HTTP 500: boom")]
                ),
            ):
                with pytest.raises(APIError, match="500"):
                    await client.get_backup_schedule("default")
        await client.close()

    @pytest.mark.asyncio
    async def test_get_backup_schedule_cloud_skips_super_mgmt(self, mock_settings):
        """Cloud mode keeps the old behavior: absence is {}, with no second GET."""
        client = UniFiClient(mock_settings)

        with patch.object(client, "resolve_site_id", new=AsyncMock(return_value="site-uuid")):
            with patch.object(
                client, "get", new=AsyncMock(side_effect=APIError("api.err.Invalid"))
            ) as mock_get:
                result = await client.get_backup_schedule("site-uuid")

        assert result == {}
        assert mock_get.await_count == 1
        await client.close()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("filename", "expected_first"),
        [
            ("autobackup_10.5.67_20261001_0430_1790829000006.unf", "/proxy/network/dl/autobackup/"),
            ("10.5.67.unf", "/proxy/network/dl/backup/"),
        ],
    )
    async def test_download_backup_local_uses_the_dl_routes(
        self, mock_settings_local, filename, expected_first
    ):
        """The controller serves scheduled backups from /dl/autobackup and manual ones (the
        trigger_backup download_url) from /dl/backup; /data/backup 404s on Network 10.5.67."""
        client = UniFiClient(mock_settings_local)
        ok = MagicMock(status_code=200, content=b"unf-bytes")
        ok.raise_for_status = MagicMock()

        with patch.object(client, "resolve_site_id", new=AsyncMock(return_value="site-uuid")):
            with patch.object(client.client, "get", new=AsyncMock(return_value=ok)) as mock_get:
                content = await client.download_backup("site-uuid", filename)

        assert content == b"unf-bytes"
        assert mock_get.await_count == 1
        assert mock_get.await_args.args[0].endswith(expected_first + filename)
        await client.close()

    @pytest.mark.asyncio
    async def test_download_backup_local_falls_back_to_the_legacy_route_on_404(
        self, mock_settings_local
    ):
        client = UniFiClient(mock_settings_local)
        missing = MagicMock(status_code=404, content=b"")
        ok = MagicMock(status_code=200, content=b"unf-bytes")
        ok.raise_for_status = MagicMock()

        with patch.object(client, "resolve_site_id", new=AsyncMock(return_value="site-uuid")):
            with patch.object(
                client.client, "get", new=AsyncMock(side_effect=[missing, ok])
            ) as mock_get:
                content = await client.download_backup("site-uuid", "10.5.67.unf")

        assert content == b"unf-bytes"
        urls = [c.args[0] for c in mock_get.await_args_list]
        assert urls[0].endswith("/proxy/network/dl/backup/10.5.67.unf")
        assert urls[1].endswith("/proxy/network/data/backup/10.5.67.unf")
        await client.close()

    @pytest.mark.asyncio
    async def test_delete_backup_local_uses_the_site_scoped_backup_command(
        self, mock_settings_local
    ):
        """The site-less DELETE /api/backup/delete-backup/<file> answers api.err.NoSiteContext
        (on an HTTP 401, which reads as an authentication failure); the backup command works."""
        client = UniFiClient(mock_settings_local)
        client._site_uuid_to_name = {"site-uuid": "default"}

        with patch.object(client, "resolve_site_id", new=AsyncMock(return_value="site-uuid")):
            with patch.object(
                client, "post", new=AsyncMock(return_value={"data": []})
            ) as mock_post:
                await client.delete_backup("site-uuid", "10.5.67.unf")

        mock_post.assert_awaited_once_with(
            "/proxy/network/api/s/default/cmd/backup",
            json_data={"cmd": "delete-backup", "filename": "10.5.67.unf"},
        )
        await client.close()


class TestUniFiClientHelpers:
    def test_looks_like_uuid_valid(self):
        assert UniFiClient._looks_like_uuid("550e8400-e29b-41d4-a716-446655440000") is True

    def test_looks_like_uuid_invalid(self):
        assert UniFiClient._looks_like_uuid("default") is False
        assert UniFiClient._looks_like_uuid("not-a-uuid") is False

    def test_looks_like_uuid_none(self):
        assert UniFiClient._looks_like_uuid(None) is False

    def test_looks_like_uuid_empty(self):
        assert UniFiClient._looks_like_uuid("") is False


SITE_UUID = "88f7af54-98f8-306a-a1c7-c9349722b1f6"


class TestIntegrationSiteResolution:
    """The local Integration API only accepts the site UUID; "default" gets
    `400 api.request.argument-type-mismatch`. wans, vpn, vouchers, hotspot,
    switching, device-tags, radius profiles, pending devices and others build those
    paths by hand from the caller's site_id, so the client resolves it."""

    @staticmethod
    def _local_client(mock_settings_local):
        mock_settings_local.get_integration_path = lambda p: f"/proxy/network/integration/v1/{p}"
        return UniFiClient(mock_settings_local)

    @staticmethod
    def _fake_controller(requested_urls):
        def respond(method, url, params=None, json=None):
            requested_urls.append(url)
            response = MagicMock()
            response.status_code = 200
            body = (
                [{"id": SITE_UUID, "internalReference": "default", "name": "Default"}]
                if url.endswith("/integration/v1/sites")
                else {"data": []}
            )
            response.json = MagicMock(return_value=body)
            response.text = "x"
            return response

        return respond

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "endpoint",
        [
            "/integration/v1/sites/default/wans",
            "/proxy/network/integration/v1/sites/default/wans",
        ],
    )
    async def test_short_name_is_sent_as_uuid(self, mock_settings_local, endpoint):
        client = self._local_client(mock_settings_local)
        urls: list[str] = []
        with patch.object(client.client, "request", side_effect=self._fake_controller(urls)):
            await client.get(endpoint)

        assert urls[-1].endswith(f"/proxy/network/integration/v1/sites/{SITE_UUID}/wans")
        assert not any("/sites/default/" in u for u in urls)
        await client.close()

    @pytest.mark.asyncio
    async def test_remainder_of_path_is_preserved(self, mock_settings_local):
        client = self._local_client(mock_settings_local)
        urls: list[str] = []
        with patch.object(client.client, "request", side_effect=self._fake_controller(urls)):
            await client.post("/integration/v1/sites/default/clients/aa:bb:cc/action", json_data={})

        assert urls[-1].endswith(f"/integration/v1/sites/{SITE_UUID}/clients/aa:bb:cc/action")
        await client.close()

    @pytest.mark.asyncio
    async def test_uuid_and_non_integration_paths_cost_no_extra_lookup(self, mock_settings_local):
        client = self._local_client(mock_settings_local)
        client._site_uuid_to_name = {SITE_UUID: "default"}  # site map already known
        with patch.object(client.client, "request", side_effect=self._fake_controller([])) as req:
            await client.get(f"/integration/v1/sites/{SITE_UUID}/wans")
            await client.get("/ea/sites/default/rest/networkconf")
            await client.get("/proxy/network/integration/v1/sites")

        # Three calls out, no site-list round trip added by the resolver.
        assert req.call_count == 3
        await client.close()

    @pytest.mark.asyncio
    async def test_unknown_site_name_raises_not_found(self, mock_settings_local):
        client = self._local_client(mock_settings_local)
        client._site_uuid_to_name = {SITE_UUID: "default"}
        with patch.object(client.client, "request", side_effect=self._fake_controller([])):
            with pytest.raises(ResourceNotFoundError):
                await client.get("/integration/v1/sites/no-such-site/wans")
        await client.close()

    @pytest.mark.asyncio
    async def test_cloud_mode_endpoint_untouched(self, mock_settings):
        client = UniFiClient(mock_settings)  # cloud-ea
        assert (
            await client._resolve_integration_site("/integration/v1/sites/default/wans")
            == "/integration/v1/sites/default/wans"
        )
        await client.close()
