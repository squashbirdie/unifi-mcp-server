"""UniFi API client with authentication, rate limiting, and error handling."""

import asyncio
import json
import re
import time
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ..config import APIType, Settings
from ..utils import (
    APIError,
    AuthenticationError,
    NetworkError,
    RateLimitError,
    ResourceNotFoundError,
    get_logger,
    log_api_request,
    validate_backup_filename,
)


class RateLimiter:
    """Token bucket rate limiter for API requests."""

    def __init__(self, requests_per_period: int, period_seconds: int) -> None:
        """Initialize rate limiter.

        Args:
            requests_per_period: Maximum requests allowed in the period
            period_seconds: Time period in seconds
        """
        self.requests_per_period = requests_per_period
        self.period_seconds = period_seconds
        self.tokens: float = float(requests_per_period)
        self.last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire a token, waiting if necessary."""
        async with self._lock:
            now = time.time()
            time_passed = now - self.last_update
            self.tokens = min(
                self.requests_per_period,
                self.tokens + (time_passed * self.requests_per_period / self.period_seconds),
            )
            self.last_update = now

            if self.tokens < 1:
                sleep_time = (1 - self.tokens) * self.period_seconds / self.requests_per_period
                await asyncio.sleep(sleep_time)
                self.tokens = 0
            else:
                self.tokens -= 1


class UniFiClient:
    """Async HTTP client for UniFi API with authentication and rate limiting."""

    # Site UUID -> internalReference ("default", etc.) map, shared across every
    # UniFiClient instance for a given controller within this process. Each tool
    # function opens a fresh `async with UniFiClient(settings) as client:`, so an
    # instance-only cache was rebuilding (and, worse, frequently NOT rebuilding —
    # see _ensure_site_map) on every single call. Keyed by base_url so distinct
    # controllers never collide.
    _SITE_MAP_CACHE: dict[str, dict[str, str]] = {}

    def __init__(self, settings: Settings) -> None:
        """Initialize UniFi API client.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self.logger = get_logger(__name__, settings.log_level)

        # Initialize HTTP client
        # Note: We construct full URLs explicitly in _request() to ensure HTTPS is preserved
        # Using base_url can cause protocol downgrade issues with httpx
        self.client = httpx.AsyncClient(
            headers=settings.get_headers(),
            timeout=settings.request_timeout,
            verify=settings.verify_ssl,
            follow_redirects=False,  # Prevent HTTP redirects that might downgrade protocol
        )

        # Initialize rate limiter
        self.rate_limiter = RateLimiter(
            settings.rate_limit_requests,
            settings.rate_limit_period,
        )

        self._authenticated = False
        self._site_id_cache: dict[str, str] = {}
        # Cache for site UUID -> internalReference mapping (needed for local API).
        # Seeded from the shared class-level cache if another instance already
        # resolved it this process.
        self._site_uuid_to_name: dict[str, str] = dict(
            self._SITE_MAP_CACHE.get(settings.base_url, {})
        )

    async def __aenter__(self) -> "UniFiClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()

    @property
    def is_authenticated(self) -> bool:
        """Check if client is authenticated.

        Returns:
            True if authenticated, False otherwise
        """
        return self._authenticated

    def _translate_endpoint(self, endpoint: str) -> str:
        """Translate endpoints based on API type.

        This method handles endpoint translation for different API modes:
        - cloud-v1: Stable v1 API (no translation for /ea/ endpoints, maps to /v1/)
        - cloud-ea: Early Access API (no translation needed)
        - local: Gateway API (translates cloud format to local format)

        Args:
            endpoint: API endpoint (e.g., /ea/sites/{site_id}/devices or /v1/hosts)

        Returns:
            Translated endpoint appropriate for the configured API type

        Examples:
            Cloud EA: /ea/sites/default/devices -> /ea/sites/default/devices (unchanged)
            Cloud V1: /v1/hosts -> /v1/hosts (unchanged)
            Local: /ea/sites/default/devices -> /proxy/network/api/s/default/devices
            Local: /ea/sites -> /proxy/network/integration/v1/sites (special case)
        """
        if self.settings.api_type in (APIType.CLOUD_V1, APIType.CLOUD_EA):
            # Cloud APIs - no translation needed
            return endpoint

        # Local API - translate cloud format to local format
        import re

        # Special case: /ea/sites (without site_id) -> Integration API
        if endpoint == "/ea/sites":
            return "/proxy/network/integration/v1/sites"

        # Pattern: /ea/sites/{site_id}/{rest_of_path}
        # Transform to: /proxy/network/api/s/{site_name}/{local_path}
        # Note: Local API uses site names (e.g., 'default'), not UUIDs
        # AND different endpoint paths than cloud API
        match = re.match(r"^/ea/sites/([^/]+)/(.+)$", endpoint)
        if match:
            site_id, cloud_path = match.groups()
            # Translate UUID to site name if we have the mapping
            site_name = self._site_uuid_to_name.get(site_id, site_id)
            if site_id != site_name:
                self.logger.debug(f"Translated site ID: {site_id} -> {site_name}")

            # Map cloud API paths to local API paths
            # Cloud API uses different endpoint naming than local API
            path_mapping = {
                "devices": "stat/device",
                "sta": "stat/sta",  # clients
                "rest/networkconf": "rest/networkconf",  # VLANs/networks
            }

            local_path = path_mapping.get(cloud_path, cloud_path)
            if cloud_path != local_path:
                self.logger.debug(f"Translated path: {cloud_path} -> {local_path}")

            return f"/proxy/network/api/s/{site_name}/{local_path}"

        # Pattern: /ea/sites/{site_id} (no trailing path)
        match = re.match(r"^/ea/sites/([^/]+)$", endpoint)
        if match:
            site_id = match.group(1)
            # Translate UUID to site name if we have the mapping
            site_name = self._site_uuid_to_name.get(site_id, site_id)
            if site_id != site_name:
                self.logger.debug(f"Translated site ID: {site_id} -> {site_name}")
            return f"/proxy/network/api/s/{site_name}/self"

        # If no pattern matches, check if it's already a local endpoint
        if endpoint.startswith("/proxy/network/"):
            # Local-mode callers occasionally build the `/proxy/network/...`
            # path directly (bypassing the /ea/sites/ translation above) —
            # e.g. site_vpn.py, and the v2 API builder in Settings. Both of
            # those still embed a site UUID rather than the short
            # internalReference the local controller actually accepts, so
            # resolve it here too rather than relying on every call site to
            # remember. Covers both known local site-scoped prefixes:
            #   /proxy/network/api/s/{id}/...          (legacy REST)
            #   /proxy/network/v2/api/site/{id}/...    (v2 API)
            for prefix_pat in (
                r"^(/proxy/network/api/s/)([^/]+)(/.*)?$",
                r"^(/proxy/network/v2/api/site/)([^/]+)(/.*)?$",
            ):
                site_match = re.match(prefix_pat, endpoint)
                if site_match:
                    prefix, site_id, rest = site_match.groups()
                    site_name = self._site_uuid_to_name.get(site_id, site_id)
                    if site_id != site_name:
                        self.logger.debug(f"Translated site ID: {site_id} -> {site_name}")
                    return f"{prefix}{site_name}{rest or ''}"
            return endpoint

        # Integration API endpoints need /proxy/network prefix on local gateway
        if endpoint.startswith("/integration/"):
            return f"/proxy/network{endpoint}"

        # V1 API endpoints need /proxy/network prefix on local gateway
        if endpoint.startswith("/v1/"):
            return f"/proxy/network{endpoint}"

        # If not recognized, return as-is and log warning
        self.logger.warning(f"Endpoint does not match known patterns: {endpoint}")
        return endpoint

    async def authenticate(self) -> None:
        """Authenticate with the UniFi API.

        Raises:
            AuthenticationError: If authentication fails
        """
        try:
            # Test authentication with a simple API call
            # Use appropriate endpoint based on API type
            if self.settings.api_type == APIType.CLOUD_V1:
                test_endpoint = "/v1/hosts"  # V1 stable API
            else:
                test_endpoint = "/ea/sites"  # EA API or local (will be auto-translated)

            response = await self._request("GET", test_endpoint)

            # Handle both dict and list responses
            # Local API (after normalization) returns list directly
            # Cloud API returns dict with "meta", "data", etc.
            if isinstance(response, list):
                # List response means we got data successfully (local API)
                self._authenticated = True
                # Build site UUID -> name mapping for local API
                if self.settings.api_type == APIType.LOCAL:
                    self._build_site_uuid_map(response)
            elif isinstance(response, dict):
                # Dict response - check for success indicators
                self._authenticated = (
                    response.get("meta", {}).get("rc") == "ok"
                    or response.get("data") is not None
                    or response.get("count") is not None
                )
            else:
                self._authenticated = False

            self.logger.info(
                f"Successfully authenticated with UniFi API (response type: {type(response).__name__})"
            )
        except Exception as e:
            self.logger.error(f"Authentication failed: {e}")
            raise AuthenticationError(f"Failed to authenticate with UniFi API: {e}") from e

    def _build_site_uuid_map(self, sites: list[dict[str, Any]]) -> None:
        """Build a mapping of site UUIDs to internal reference names.

        This is required for local API, which uses site names (e.g., 'default')
        instead of UUIDs in endpoint paths.

        Args:
            sites: List of site objects from /ea/sites endpoint
        """
        self._site_uuid_to_name.clear()
        for site in sites:
            if not isinstance(site, dict):
                self.logger.warning(f"Skipping non-dict site entry: {type(site).__name__}")
                continue
            site_id = site.get("id")
            internal_ref = site.get("internalReference")
            if site_id and internal_ref:
                self._site_uuid_to_name[site_id] = internal_ref

        self.logger.info(f"Built site UUID mapping: {len(self._site_uuid_to_name)} sites")
        # Publish to the shared cache so every OTHER UniFiClient instance
        # against this same controller skips the round trip entirely.
        self._SITE_MAP_CACHE[self.settings.base_url] = dict(self._site_uuid_to_name)

    async def _ensure_site_map(self) -> None:
        """Lazily resolve the site UUID -> internalReference map for local-API
        calls that need it.

        Most tool functions build endpoints as `/ea/sites/{site_id}/...` (or
        `/proxy/network/v2/api/site/{site_id}/...`) using whatever site_id the
        caller passed in — usually the public UUID, since that is what every
        other endpoint on this fleet returns. The local controller's own REST
        and v2 APIs reject a UUID here with `api.err.NoSiteContext`; they only
        accept the short internalReference ("default"). Previously this map
        was populated only as a side effect of `authenticate()`, which most
        tool functions never call before making their real request — silently
        breaking every endpoint that embeds a site UUID. This makes the
        resolution unconditional and self-healing instead of opt-in.
        """
        if self.settings.api_type != APIType.LOCAL or self._site_uuid_to_name:
            return
        cached = self._SITE_MAP_CACHE.get(self.settings.base_url)
        if cached:
            self._site_uuid_to_name.update(cached)
            return
        response = await self._request("GET", "/ea/sites")
        sites = response if isinstance(response, list) else response.get("data", [])
        self._build_site_uuid_map(sites)

    async def _resolve_integration_site(self, endpoint: str) -> str:
        """Swap a short site name for its UUID in Integration API paths.

        The local controller's Integration API (`/integration/v1/sites/{siteId}/...`)
        only accepts the site UUID and answers a short name such as "default" with
        `400 api.request.argument-type-mismatch`. Every other tool family takes the
        short name happily, so callers pass "default" everywhere and the tools that
        build Integration paths by hand (wans, vpn, vouchers, hotspot, switching,
        reference data, ...) broke. Resolve it here, once, instead of at each call
        site. UUIDs pass through untouched, so existing callers keep working.

        Args:
            endpoint: Request path as passed to ``_request``.

        Returns:
            The endpoint with a UUID site segment, or the original endpoint when it
            is not a local Integration API site path or already carries a UUID.

        Raises:
            ResourceNotFoundError: If the site name matches no site on the controller.
        """
        if self.settings.api_type != APIType.LOCAL:
            return endpoint
        match = re.match(r"^((?:/proxy/network)?/integration/v1/sites/)([^/?]+)(.*)$", endpoint)
        if not match:
            return endpoint
        prefix, site, rest = match.groups()
        if self._looks_like_uuid(site):
            return endpoint
        return f"{prefix}{await self.resolve_site_id(site)}{rest}"

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        retry_count: int = 0,
    ) -> dict[str, Any]:
        """Make an HTTP request with retries and error handling.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path
            params: Query parameters
            json_data: JSON request body
            retry_count: Current retry attempt number

        Returns:
            Response data as dictionary

        Raises:
            APIError: If API returns an error
            RateLimitError: If rate limit is exceeded
            NetworkError: If network communication fails
        """
        # Apply rate limiting
        await self.rate_limiter.acquire()

        # Resolve the site UUID->name map before any request that might need
        # it. Skip for the bootstrap "/ea/sites" call itself — that IS the
        # request _ensure_site_map issues to populate the map, so calling it
        # again here would recurse forever.
        if endpoint != "/ea/sites":
            await self._ensure_site_map()
            endpoint = await self._resolve_integration_site(endpoint)

        start_time = time.time()

        try:
            # Automatically translate endpoint based on API type
            translated_endpoint = self._translate_endpoint(endpoint)

            # ENHANCED LOGGING - Use INFO level to ensure visibility
            if endpoint != translated_endpoint:
                self.logger.info(f"Endpoint translation: {endpoint} -> {translated_endpoint}")

            # Construct full URL explicitly to ensure HTTPS protocol is preserved
            # httpx's base_url joining can have issues with protocol handling
            full_url = (
                f"{self.settings.base_url}{translated_endpoint}"
                if translated_endpoint.startswith("/")
                else translated_endpoint
            )

            # CRITICAL: Ensure HTTPS scheme - force replace http:// with https://
            if full_url.startswith("http://"):
                full_url = full_url.replace("http://", "https://", 1)
                self.logger.warning(f"Force-corrected HTTP to HTTPS: {full_url}")

            # ENHANCED LOGGING - Show actual URL being requested
            self.logger.info(f"Making {method} request to: {full_url}")

            response = await self.client.request(
                method=method,
                url=full_url,
                params=params,
                json=json_data,
            )

            duration_ms = (time.time() - start_time) * 1000

            # Log request if enabled
            if self.settings.log_api_requests:
                log_api_request(
                    self.logger,
                    method=method,
                    url=translated_endpoint,  # Log the translated endpoint, not the original
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))

                # Retry if we haven't exceeded max retries
                if retry_count < self.settings.max_retries:
                    self.logger.warning(f"Rate limited, retrying after {retry_after}s")
                    await asyncio.sleep(retry_after)
                    return await self._request(method, endpoint, params, json_data, retry_count + 1)

                raise RateLimitError(retry_after=retry_after)

            # Handle not found
            if response.status_code == 404:
                raise ResourceNotFoundError("resource", endpoint)

            # Handle authentication errors
            if response.status_code in (401, 403):
                raise AuthenticationError(f"Authentication failed: {response.text}")

            # Handle other errors
            if response.status_code >= 400:
                error_data = None
                try:
                    error_data = response.json()
                except Exception:
                    pass

                raise APIError(
                    message=f"API request failed: {response.text}",
                    status_code=response.status_code,
                    response_data=error_data,
                )

            # Parse response - handle empty responses from local gateway
            try:
                if response.text and response.text.strip():
                    json_response: dict[str, Any] = response.json()

                    # Normalize response format based on API type
                    # Cloud V1 API returns: {"data": [...], "httpStatusCode": 200, "traceId": "..."}
                    # Local API returns: {"data": [...], "count": N, "totalCount": N}
                    # Cloud EA API returns: {...} or [...] directly
                    if isinstance(json_response, dict) and "data" in json_response:
                        # Both cloud v1 and local API wrap data in a "data" field
                        data = json_response["data"]
                        api_type = (
                            self.settings.api_type.value
                            if hasattr(self.settings.api_type, "value")
                            else str(self.settings.api_type)
                        )
                        self.logger.debug(
                            f"Normalized {api_type} API response: extracted {len(data) if isinstance(data, list) else 'N/A'} items"
                        )
                        # Return a normalized dict with data key for consistency across APIs
                        # Always return a dict[str, Any]
                        return {"data": data}
                else:
                    # Empty response body - treat as success with empty data
                    self.logger.debug(f"Empty response body for {endpoint}, returning empty dict")
                    json_response = {}
                return json_response
            except (ValueError, json.JSONDecodeError) as e:
                # Invalid JSON - log and return empty dict for successful status codes
                self.logger.warning(f"Invalid JSON in response for {endpoint}: {e}")
                return {}

        except httpx.TimeoutException as e:
            # Retry on timeout
            if retry_count < self.settings.max_retries:
                backoff = self.settings.retry_backoff_factor**retry_count
                self.logger.warning(f"Request timeout, retrying in {backoff}s")
                await asyncio.sleep(backoff)
                return await self._request(method, endpoint, params, json_data, retry_count + 1)

            raise NetworkError(f"Request timeout: {e}") from e

        except httpx.NetworkError as e:
            # Retry on network error
            if retry_count < self.settings.max_retries:
                backoff = self.settings.retry_backoff_factor**retry_count
                self.logger.warning(f"Network error, retrying in {backoff}s")
                await asyncio.sleep(backoff)
                return await self._request(method, endpoint, params, json_data, retry_count + 1)

            raise NetworkError(f"Network communication failed: {e}") from e

        except (RateLimitError, AuthenticationError, APIError, ResourceNotFoundError):
            # Re-raise our custom exceptions
            raise

        except Exception as e:
            self.logger.error(f"Unexpected error during API request: {e}")
            raise APIError(f"Unexpected error: {e}") from e

    async def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make a GET request.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            Response data
        """
        return await self._request("GET", endpoint, params=params)

    async def post(
        self,
        endpoint: str,
        json_data: dict[str, Any],
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a POST request.

        Args:
            endpoint: API endpoint path
            json_data: JSON request body
            params: Query parameters

        Returns:
            Response data
        """
        return await self._request("POST", endpoint, params=params, json_data=json_data)

    async def put(
        self,
        endpoint: str,
        json_data: dict[str, Any],
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a PUT request.

        Args:
            endpoint: API endpoint path
            json_data: JSON request body
            params: Query parameters

        Returns:
            Response data
        """
        return await self._request("PUT", endpoint, params=params, json_data=json_data)

    async def delete(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make a DELETE request.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            Response data
        """
        return await self._request("DELETE", endpoint, params=params)

    @staticmethod
    def _looks_like_uuid(value: str | None) -> bool:
        """Determine whether a string value appears to be a UUID."""
        if not value:
            return False

        try:
            UUID(value)
            return True
        except (ValueError, TypeError):
            return False

    async def resolve_site_id(self, site_identifier: str | None) -> str:
        """Resolve a user-provided site identifier to the controller's UUID format.

        Args:
            site_identifier: Friendly site identifier (e.g., "default" or UUID)

        Returns:
            Resolved UUID for the site (or the original identifier for cloud API)

        Raises:
            ResourceNotFoundError: If the site cannot be located
        """
        if not site_identifier:
            site_identifier = self.settings.default_site

        if self.settings.api_type == APIType.CLOUD or self._looks_like_uuid(site_identifier):
            return site_identifier

        cached = self._site_id_cache.get(site_identifier)
        if cached:
            return cached

        sites_endpoint = self.settings.get_integration_path("sites")
        response = await self.get(sites_endpoint)
        # Handle both list (when API returns {"data": [...]}) and dict responses
        if isinstance(response, list):
            sites = response
        else:
            sites = response.get("data", response.get("sites", []))

        for site in sites:
            if not isinstance(site, dict):
                self.logger.warning(
                    f"Skipping non-dict site entry in resolve: {type(site).__name__}"
                )
                continue
            site_id = site.get("id") or site.get("_id")
            if not site_id:
                continue

            identifiers = {
                site_id,
                site.get("internalReference"),
                site.get("name"),
                site.get("shortName"),
            }

            if site_identifier in {value for value in identifiers if value}:
                site_id_str = str(site_id)
                self._site_id_cache[site_identifier] = site_id_str
                return site_id_str

        raise ResourceNotFoundError("site", site_identifier)

    # Backup and Restore Operations

    async def trigger_backup(
        self,
        site_id: str,
        backup_type: str = "network",
        days: int = -1,
    ) -> dict[str, Any]:
        """Trigger a backup operation on the UniFi controller.

        Args:
            site_id: Site identifier
            backup_type: Type of backup ("network" for network-only, "system" for full)
            days: Number of days to retain backup (-1 for indefinite)

        Returns:
            Backup operation response including download URL

        Note:
            For local API, use: /proxy/network/api/s/{site}/cmd/backup
            Response contains a URL in data.url for downloading the backup file
        """
        site_id = await self.resolve_site_id(site_id)

        # For local API, translate to local endpoint format
        if self.settings.api_type == APIType.LOCAL:
            # Use site name (e.g., "default") not UUID for local API
            site_name = self._site_uuid_to_name.get(site_id, site_id)
            endpoint = f"/proxy/network/api/s/{site_name}/cmd/backup"
        else:
            # Cloud API
            endpoint = f"/ea/sites/{site_id}/cmd/backup"

        payload = {
            "cmd": "backup",
            "days": str(days),
        }

        return await self.post(endpoint, json_data=payload)

    async def list_backups(self, site_id: str) -> list[dict[str, Any]]:
        """List all available backups for a site.

        Args:
            site_id: Site identifier

        Returns:
            List of backup metadata dictionaries

        Note:
            For local API: POST /proxy/network/api/s/{site}/cmd/backup
            with body {"cmd": "list-backups"}
        """
        site_id = await self.resolve_site_id(site_id)

        # Backups are listed with the backup command, scoped to a site. The
        # previous site-less GET /api/backup/list-backups had no site context,
        # so the controller rejected it with api.err.NoSiteContext -- carried
        # on an HTTP 401, which this client then reported as an
        # authentication failure. Verified live on Network 10.5.67.
        if self.settings.api_type == APIType.LOCAL:
            site_name = self._site_uuid_to_name.get(site_id, site_id)
            endpoint = f"/proxy/network/api/s/{site_name}/cmd/backup"
        else:
            # Cloud API
            endpoint = f"/ea/sites/{site_id}/cmd/backup"

        response = await self.post(endpoint, json_data={"cmd": "list-backups"})

        # Handle different response formats
        if isinstance(response, list):
            return response
        data = (
            response.get("data", response.get("backups", [])) if isinstance(response, dict) else []
        )
        if isinstance(data, list):
            return data
        return []

    async def download_backup(
        self,
        site_id: str,
        backup_filename: str,
    ) -> bytes:
        """Download a backup file.

        Args:
            site_id: Site identifier
            backup_filename: Backup filename to download

        Returns:
            Backup file content as bytes

        Note:
            This method downloads the actual backup file content. For the local API the controller
            serves scheduled backups (``autobackup_*``) from ``/proxy/network/dl/autobackup/{filename}``
            and manual ones (what ``trigger_backup`` returns as ``download_url``) from
            ``/proxy/network/dl/backup/{filename}``; ``/proxy/network/data/backup/{filename}`` is tried
            last, because it 404s on Network 10.5.67 for both.
        """
        site_id = await self.resolve_site_id(site_id)
        backup_filename = validate_backup_filename(backup_filename)
        safe_name = quote(backup_filename, safe="")

        if self.settings.api_type == APIType.LOCAL:
            routes = (
                [f"/proxy/network/dl/autobackup/{safe_name}"]
                if backup_filename.startswith("autobackup_")
                else [f"/proxy/network/dl/backup/{safe_name}"]
            )
            routes.append(f"/proxy/network/data/backup/{safe_name}")
        else:
            # Cloud API
            routes = [f"/ea/sites/{site_id}/backups/{safe_name}/download"]

        # Use direct HTTP client for binary download
        response = await self.client.get(f"{self.settings.base_url}{routes[0]}")
        for endpoint in routes[1:]:
            if response.status_code != 404:
                break
            response = await self.client.get(f"{self.settings.base_url}{endpoint}")
        response.raise_for_status()

        return response.content

    async def delete_backup(
        self,
        site_id: str,
        backup_filename: str,
    ) -> dict[str, Any]:
        """Delete a specific backup file.

        Args:
            site_id: Site identifier
            backup_filename: Backup filename to delete

        Returns:
            Deletion confirmation response

        Note:
            For the local API this uses the site-scoped backup command, like ``list_backups``:
            POST /proxy/network/api/s/{site}/cmd/backup with ``{"cmd": "delete-backup", "filename": ...}``.
            The earlier site-less ``DELETE /api/backup/delete-backup/{filename}`` has no site context and
            the controller answers it with api.err.NoSiteContext on an HTTP 401 (reported here as an
            authentication failure).
        """
        site_id = await self.resolve_site_id(site_id)
        backup_filename = validate_backup_filename(backup_filename)

        if self.settings.api_type == APIType.LOCAL:
            site_name = self._site_uuid_to_name.get(site_id, site_id)
            return await self.post(
                f"/proxy/network/api/s/{site_name}/cmd/backup",
                json_data={"cmd": "delete-backup", "filename": backup_filename},
            )

        # Cloud API
        return await self.delete(f"/ea/sites/{site_id}/backups/{quote(backup_filename, safe='')}")

    async def restore_backup(
        self,
        site_id: str,
        backup_filename: str,
    ) -> dict[str, Any]:
        """Restore the controller from a backup file.

        Args:
            site_id: Site identifier
            backup_filename: Backup filename to restore from

        Returns:
            Restore operation response

        Warning:
            This is a destructive operation that will restore the controller
            to the state captured in the backup. Use with extreme caution.

        Note:
            For local API: POST /proxy/network/api/backup/restore
            Controller may restart during restore process
        """
        site_id = await self.resolve_site_id(site_id)

        # For local API
        if self.settings.api_type == APIType.LOCAL:
            endpoint = "/proxy/network/api/backup/restore"
            payload = {"filename": backup_filename}
        else:
            # Cloud API
            endpoint = f"/ea/sites/{site_id}/backups/{backup_filename}/restore"
            payload = {"backup_id": backup_filename}

        return await self.post(endpoint, json_data=payload)

    async def get_backup_status(
        self,
        site_id: str,
        operation_id: str,
    ) -> dict[str, Any]:
        """Get the status of an ongoing backup operation.

        Args:
            site_id: Site identifier
            operation_id: Backup operation ID

        Returns:
            Operation status including progress and any errors
        """
        site_id = await self.resolve_site_id(site_id)

        # For local API
        if self.settings.api_type == APIType.LOCAL:
            site_name = self._site_uuid_to_name.get(site_id, site_id)
            endpoint = f"/proxy/network/api/s/{site_name}/stat/backup/{operation_id}"
        else:
            # Cloud API
            endpoint = f"/ea/sites/{site_id}/operations/{operation_id}"

        return await self.get(endpoint)

    async def get_restore_status(
        self,
        operation_id: str,
    ) -> dict[str, Any]:
        """Get the status of an ongoing restore operation.

        Args:
            operation_id: Restore operation ID

        Returns:
            Operation status including progress, step, and any errors
        """
        # UniFi does not expose a dedicated restore-status endpoint; return a
        # response that honestly reflects this limitation rather than
        # falsely claiming the restore is complete.
        return {
            "status": "not_supported",
            "message": "Restore status tracking is not available via the UniFi API.",
            "operation_id": operation_id,
        }

    async def configure_backup_schedule(
        self,
        site_id: str,
        backup_type: str = "network",
        frequency: str = "daily",
        time_of_day: str = "02:00",
        enabled: bool = True,
        retention_days: int = 30,
        max_backups: int = 10,
        day_of_week: str | int | None = None,
        day_of_month: int | None = None,
        cloud_backup_enabled: bool = False,
    ) -> dict[str, Any]:
        """Configure the automated backup schedule for a site.

        Args:
            site_id: Site identifier
            backup_type: Type of backup ("network" or "system")
            frequency: Schedule frequency ("daily", "weekly", "monthly")
            time_of_day: Time to run backup in HH:MM format
            enabled: Whether the schedule is active
            retention_days: Number of days to keep backups
            max_backups: Maximum number of backups to retain
            day_of_week: Day of week for weekly schedules; a day name
                ("monday") or the tool layer's integer form (0=Monday
                through 6=Sunday)
            day_of_month: Day of month for monthly schedules (1-28)
            cloud_backup_enabled: Whether to also push backups to cloud storage

        Returns:
            Schedule configuration response

        Note:
            For local API: PUT
            /proxy/network/api/s/{site}/set/setting/auto_backup/{settings_id}
        """
        # Translate the weekday into a cron day NAME before any network
        # round-trip. The tool layer documents integers as
        # 0=Monday..6=Sunday, which is not cron's numbering (cron counts
        # 0=Sunday) -- and Monday's 0 is falsy, so a bare f-string default
        # would silently turn Monday into the fallback. Names sidestep both
        # traps.
        cron_day_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        if day_of_week is None:
            cron_dow = "sun"
        elif isinstance(day_of_week, int):
            if not 0 <= day_of_week <= 6:
                raise APIError(
                    f"day_of_week must be 0 (Monday) through 6 (Sunday), got {day_of_week}"
                )
            cron_dow = cron_day_names[day_of_week]
        else:
            cron_dow = str(day_of_week).strip().lower()[:3]
            if cron_dow not in cron_day_names:
                raise APIError(f"day_of_week must be a weekday name, got {day_of_week!r}")

        site_id = await self.resolve_site_id(site_id)

        # The schedule lives in the auto_backup settings section; the
        # rest/backup/schedule resource this method previously PUT to does
        # not exist on any controller (api.err.InvalidObject). UniFi OS
        # consoles do not carry the section at all -- their scheduled
        # backups are managed at the console level -- so absence is reported
        # as such rather than written into.
        current = await self.get_backup_schedule(site_id)
        settings_id = current.get("_id")
        if not settings_id:
            raise APIError(
                "This controller has no auto_backup settings section, so the "
                "backup schedule cannot be configured through the Network "
                "API. UniFi OS consoles manage scheduled backups at the "
                "console level (existing backups are still visible via "
                "list_backups)."
            )

        hour, _, minute = time_of_day.partition(":")
        cron_map = {
            "daily": f"{minute or 0} {hour or 0} * * *",
            "weekly": f"{minute or 0} {hour or 0} * * {cron_dow}",
            "monthly": f"{minute or 0} {hour or 0} {day_of_month or 1} * *",
        }
        payload: dict[str, Any] = {
            "auto_backup_enabled": enabled,
            "auto_backup_cron_expr": cron_map.get(frequency, cron_map["daily"]),
            "auto_backup_max_files": max_backups,
            "auto_backup_days": retention_days,
        }

        site_name = self._site_uuid_to_name.get(site_id, site_id)
        if self.settings.api_type == APIType.LOCAL:
            endpoint = f"/proxy/network/api/s/{site_name}/set/setting/auto_backup/{settings_id}"
        else:
            endpoint = f"/ea/sites/{site_id}/set/setting/auto_backup/{settings_id}"

        return await self.put(endpoint, json_data=payload)

    async def get_backup_schedule(
        self,
        site_id: str,
    ) -> dict[str, Any]:
        """Retrieve the current backup schedule configuration for a site.

        Args:
            site_id: Site identifier

        Returns:
            Backup schedule configuration, or empty dict if none is configured

        Note:
            For local API: GET
            /proxy/network/api/s/{site}/get/setting/auto_backup

            UniFi OS consoles (UDM/UCG) do not expose the ``auto_backup``
            settings section -- the request fails with ``api.err.Invalid`` --
            but the autobackup schedule still exists, stored inside the
            ``super_mgmt`` site setting under ``autobackup_*`` field names
            (verified on UniFi OS 5.1.33 / Network 10.6.106, see issue #190).
            When the primary section is absent, fall back to ``super_mgmt``
            and normalize its fields so callers see one shape either way.
        """
        site_id = await self.resolve_site_id(site_id)

        # The schedule is the auto_backup settings section. Absence (or the
        # api.err.Invalid a UniFi OS console answers with) means scheduled
        # backups may be managed at the console level, not through this API.
        if self.settings.api_type == APIType.LOCAL:
            site_name = self._site_uuid_to_name.get(site_id, site_id)
            endpoint = f"/proxy/network/api/s/{site_name}/get/setting/auto_backup"
        else:
            site_name = site_id
            endpoint = f"/ea/sites/{site_id}/get/setting/auto_backup"

        try:
            response = await self.get(endpoint)
        except APIError as exc:
            # Only the controller's "no such setting" answers mean absence;
            # anything else (500s, validation failures) is a real error the
            # caller must see, not a console-level-backups condition.
            message = str(exc)
            if any(
                marker in message
                for marker in ("api.err.Invalid", "api.err.NotFound", "api.err.NoSuchObject")
            ):
                if self.settings.api_type == APIType.LOCAL:
                    return await self._get_backup_schedule_from_super_mgmt(site_name)
                return {}
            raise

        items = response if isinstance(response, list) else response.get("data", [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get("key") == "auto_backup":
                    return item
            return items[0] if items and isinstance(items[0], dict) else {}
        return items if isinstance(items, dict) else {}

    async def _get_backup_schedule_from_super_mgmt(self, site_name: str) -> dict[str, Any]:
        """Read the autobackup schedule from the ``super_mgmt`` site setting.

        UniFi OS consoles reject ``get/setting/auto_backup`` with
        ``api.err.Invalid`` but keep the configured schedule in
        ``super_mgmt`` under ``autobackup_*`` names. This fallback only runs
        after the primary section was proven absent, and it only reports a
        schedule when autobackup fields are actually present -- a super_mgmt
        response without them means backups really are console-managed.

        Args:
            site_name: Resolved site short name for the legacy path

        Returns:
            Schedule normalized to ``auto_backup_*`` field names, or {} when
            no autobackup configuration exists
        """
        endpoint = f"/proxy/network/api/s/{site_name}/get/setting/super_mgmt"
        try:
            response = await self.get(endpoint)
        except APIError as exc:
            message = str(exc)
            if any(
                marker in message
                for marker in ("api.err.Invalid", "api.err.NotFound", "api.err.NoSuchObject")
            ):
                return {}
            raise

        items = response if isinstance(response, list) else response.get("data", [])
        candidates: list[Any]
        if isinstance(items, dict):
            candidates = [items]
        elif isinstance(items, list):
            candidates = [item for item in items if isinstance(item, dict)]
        else:
            candidates = []

        # The schedule fields live directly on the super_mgmt object; prefer
        # an entry that actually carries them, and accept a single-object
        # envelope otherwise.
        super_mgmt = next(
            (item for item in candidates if "autobackup_enabled" in item),
            candidates[0] if len(candidates) == 1 else None,
        )

        if not super_mgmt or "autobackup_enabled" not in super_mgmt:
            return {}

        # Normalize autobackup_* -> auto_backup_* so the tool layer consumes
        # one field shape regardless of which section answered.
        normalized: dict[str, Any] = {"key": "auto_backup", "_id": super_mgmt.get("_id", "")}
        for target, source in (
            ("auto_backup_enabled", "autobackup_enabled"),
            ("auto_backup_cron_expr", "autobackup_cron_expr"),
            ("auto_backup_timezone", "autobackup_timezone"),
            ("auto_backup_days", "autobackup_days"),
            ("auto_backup_max_files", "autobackup_max_files"),
        ):
            if source in super_mgmt:
                normalized[target] = super_mgmt[source]
        return normalized
