"""Unit tests for src/resources/sites.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.resources.sites import SitesResource


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.log_level = "INFO"
    return settings


def create_mock_client(response):
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.authenticate = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


def make_site(site_id, name="Test Site"):
    return {"_id": site_id, "name": name, "desc": "Test Description"}


class TestSitesResource:
    def test_init(self, mock_settings):
        resource = SitesResource(mock_settings)
        assert resource.settings == mock_settings

    @pytest.mark.asyncio
    async def test_list_sites_success(self, mock_settings):
        response = {"data": [make_site("site-1"), make_site("site-2")]}

        with patch("src.resources.sites.UniFiClient") as mock_client_class:
            mock_client_class.return_value = create_mock_client(response)

            resource = SitesResource(mock_settings)
            result = await resource.list_sites()

            assert len(result) == 2
            assert result[0].id == "site-1"

    @pytest.mark.asyncio
    async def test_list_sites_with_pagination(self, mock_settings):
        response = {"data": [make_site(f"site-{i}") for i in range(10)]}

        with patch("src.resources.sites.UniFiClient") as mock_client_class:
            mock_client_class.return_value = create_mock_client(response)

            resource = SitesResource(mock_settings)
            result = await resource.list_sites(limit=3, offset=2)

            assert len(result) == 3

    @pytest.mark.asyncio
    async def test_get_site_by_id(self, mock_settings):
        response = {"data": [make_site("site-123", "Main Site")]}

        with patch("src.resources.sites.UniFiClient") as mock_client_class:
            mock_client_class.return_value = create_mock_client(response)

            resource = SitesResource(mock_settings)
            result = await resource.get_site("site-123")

            assert result is not None
            assert result.id == "site-123"
            assert result.name == "Main Site"

    @pytest.mark.asyncio
    async def test_get_site_by_name(self, mock_settings):
        response = {"data": [make_site("site-abc", "Office")]}

        with patch("src.resources.sites.UniFiClient") as mock_client_class:
            mock_client_class.return_value = create_mock_client(response)

            resource = SitesResource(mock_settings)
            result = await resource.get_site("Office")

            assert result is not None
            assert result.name == "Office"

    @pytest.mark.asyncio
    async def test_get_site_not_found(self, mock_settings):
        response = {"data": [make_site("other-site")]}

        with patch("src.resources.sites.UniFiClient") as mock_client_class:
            mock_client_class.return_value = create_mock_client(response)

            resource = SitesResource(mock_settings)
            result = await resource.get_site("nonexistent")

            assert result is None

    def test_get_uri_with_site_id(self, mock_settings):
        resource = SitesResource(mock_settings)
        uri = resource.get_uri("site-123")
        assert uri == "sites://site-123"

    def test_get_uri_without_site_id(self, mock_settings):
        resource = SitesResource(mock_settings)
        uri = resource.get_uri()
        assert uri == "sites://"
