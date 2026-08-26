"""Unit tests for diagnostics tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.diagnostics import (
    get_network_references,
    get_spectrum_scan,
    get_speed_test_history,
    get_speed_test_status,
    list_spectrum_interference,
    run_speed_test,
)
from src.utils.exceptions import ValidationError


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    settings = MagicMock()
    settings.log_level = "INFO"
    settings.api_type = MagicMock()
    settings.api_type.value = "cloud-ea"
    settings.base_url = "https://api.ui.com"
    settings.api_key = "test-key"
    return settings


def create_mock_client(get_responses=None):
    """Create a mock UniFiClient with configurable GET responses."""
    mock_client = AsyncMock()
    if get_responses:
        mock_client.get = AsyncMock(side_effect=get_responses)
    else:
        mock_client.get = AsyncMock(return_value={"data": []})
    mock_client.post = AsyncMock(return_value={})
    mock_client.authenticate = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


class TestGetNetworkReferences:
    @pytest.mark.asyncio
    async def test_get_network_references_success(self, mock_settings):
        """Test successful retrieval of network references."""
        response = {
            "data": {
                "referenceResources": [
                    {
                        "id": "ref-1",
                        "name": "Main WiFi",
                        "type": "wifi",
                        "resource_type": "broadcast",
                    },
                    {
                        "id": "ref-2",
                        "name": "Port Profile 1",
                        "type": "port_profile",
                        "resource_type": "switching",
                    },
                ]
            }
        }

        with patch("src.tools.diagnostics.UniFiClient") as mock_client_class:
            mock_client_class.return_value = create_mock_client([response])

            result = await get_network_references("site-1", "net-123", mock_settings)

            assert isinstance(result, dict)
            assert "references" in result
            assert len(result["references"]) == 2
            assert result["references"][0]["name"] == "Main WiFi"
            assert result["references"][1]["type"] == "port_profile"
            assert result["network_id"] == "net-123"

    @pytest.mark.asyncio
    async def test_get_network_references_empty(self, mock_settings):
        """Test network references with empty response."""
        response = {"data": {"referenceResources": []}}

        with patch("src.tools.diagnostics.UniFiClient") as mock_client_class:
            mock_client_class.return_value = create_mock_client([response])

            result = await get_network_references("site-1", "net-123", mock_settings)

            assert result["references"] == []
            assert result["network_id"] == "net-123"

    @pytest.mark.asyncio
    async def test_get_network_references_invalid_site_id(self, mock_settings):
        """Test validation error for empty site_id."""
        with pytest.raises(ValidationError):
            await get_network_references("", "net-123", mock_settings)


class TestRunSpeedTest:
    @pytest.mark.asyncio
    async def test_run_speed_test_success(self, mock_settings):
        """Test successful speed test initiation."""
        response = {"data": {"status": "started", "test_id": "st-123"}}

        with patch("src.tools.diagnostics.UniFiClient") as mock_client_class:
            mock_client_class.return_value = create_mock_client()
            mock_client_class.return_value.post = AsyncMock(return_value=response)

            result = await run_speed_test("site-1", mock_settings)

            assert isinstance(result, dict)
            assert result["status"] == "started"
            assert result["test_id"] == "st-123"
            assert result["site_id"] == "site-1"

    @pytest.mark.asyncio
    async def test_run_speed_test_invalid_site_id(self, mock_settings):
        """Test validation error for empty site_id."""
        with pytest.raises(ValidationError):
            await run_speed_test("", mock_settings)


class TestGetSpeedTestStatus:
    @pytest.mark.asyncio
    async def test_get_speed_test_status_success(self, mock_settings):
        """Test successful retrieval of speed test status."""
        response = {
            "data": {
                "status": "completed",
                "download_speed_mbps": 850.5,
                "upload_speed_mbps": 420.2,
                "ping_ms": 12.3,
                "jitter_ms": 2.1,
                "timestamp": "2025-01-15T10:30:00Z",
            }
        }

        with patch("src.tools.diagnostics.UniFiClient") as mock_client_class:
            mock_client_class.return_value = create_mock_client([response])

            result = await get_speed_test_status("site-1", mock_settings)

            assert isinstance(result, dict)
            assert result["status"] == "completed"
            assert result["download_speed_mbps"] == 850.5
            assert result["upload_speed_mbps"] == 420.2
            assert result["ping_ms"] == 12.3

    @pytest.mark.asyncio
    async def test_get_speed_test_status_running(self, mock_settings):
        """Test speed test status when still running."""
        response = {"data": {"status": "running"}}

        with patch("src.tools.diagnostics.UniFiClient") as mock_client_class:
            mock_client_class.return_value = create_mock_client([response])

            result = await get_speed_test_status("site-1", mock_settings)

            assert result["status"] == "running"

    @pytest.mark.asyncio
    async def test_get_speed_test_status_invalid_site_id(self, mock_settings):
        """Test validation error for empty site_id."""
        with pytest.raises(ValidationError):
            await get_speed_test_status("", mock_settings)


class TestGetSpeedTestHistory:
    @pytest.mark.asyncio
    async def test_get_speed_test_history_success(self, mock_settings):
        """Test successful retrieval of speed test history."""
        response = {
            "data": [
                {
                    "id": "st-1",
                    "status": "completed",
                    "download_speed_mbps": 850.5,
                    "upload_speed_mbps": 420.2,
                    "ping_ms": 12.3,
                    "timestamp": "2025-01-15T10:30:00Z",
                },
                {
                    "id": "st-2",
                    "status": "completed",
                    "download_speed_mbps": 900.1,
                    "upload_speed_mbps": 450.5,
                    "ping_ms": 10.5,
                    "timestamp": "2025-01-14T10:30:00Z",
                },
            ]
        }

        with patch("src.tools.diagnostics.UniFiClient") as mock_client_class:
            mock_client_class.return_value = create_mock_client([response])

            result = await get_speed_test_history("site-1", mock_settings)

            assert isinstance(result, list)
            assert len(result) == 2
            assert result[0]["id"] == "st-1"
            assert result[0]["download_speed_mbps"] == 850.5
            assert result[1]["id"] == "st-2"

    @pytest.mark.asyncio
    async def test_get_speed_test_history_empty(self, mock_settings):
        """Test speed test history with empty response."""
        response = {"data": []}

        with patch("src.tools.diagnostics.UniFiClient") as mock_client_class:
            mock_client_class.return_value = create_mock_client([response])

            result = await get_speed_test_history("site-1", mock_settings)

            assert result == []

    @pytest.mark.asyncio
    async def test_get_speed_test_history_list_response(self, mock_settings):
        """Test speed test history with direct list response."""
        response = [
            {
                "id": "st-1",
                "status": "completed",
                "download_speed_mbps": 500.0,
                "upload_speed_mbps": 200.0,
                "timestamp": "2025-01-15T10:30:00Z",
            }
        ]

        with patch("src.tools.diagnostics.UniFiClient") as mock_client_class:
            mock_client_class.return_value = create_mock_client([response])

            result = await get_speed_test_history("site-1", mock_settings)

            assert len(result) == 1
            assert result[0]["id"] == "st-1"

    @pytest.mark.asyncio
    async def test_get_speed_test_history_invalid_site_id(self, mock_settings):
        """Test validation error for empty site_id."""
        with pytest.raises(ValidationError):
            await get_speed_test_history("", mock_settings)


class TestGetSpectrumScan:
    @pytest.mark.asyncio
    async def test_get_spectrum_scan_success(self, mock_settings):
        """Test successful retrieval of spectrum scan."""
        response = {
            "data": [
                {
                    "device_id": "device-1",
                    "device_name": "AP-LivingRoom",
                    "frequency_band": "5",
                    "channel": 36,
                    "noise_floor_dbm": -95.0,
                    "utilization_percent": 45.2,
                    "timestamp": "2025-01-15T10:30:00Z",
                    "scan_data": [{"freq": 5180, "noise": -92, "util": 40}],
                }
            ]
        }

        with patch("src.tools.diagnostics.UniFiClient") as mock_client_class:
            mock_client_class.return_value = create_mock_client([response])

            result = await get_spectrum_scan("site-1", mock_settings)

            assert isinstance(result, dict)
            assert result["device_id"] == "device-1"
            assert result["device_name"] == "AP-LivingRoom"
            assert result["frequency_band"] == "5"
            assert result["channel"] == 36

    @pytest.mark.asyncio
    async def test_get_spectrum_scan_list_response(self, mock_settings):
        """Test spectrum scan with direct list response."""
        response = [
            {
                "device_id": "device-1",
                "device_name": "AP-LivingRoom",
                "frequency_band": "2.4",
                "channel": 6,
                "noise_floor_dbm": -88.0,
                "utilization_percent": 65.0,
                "timestamp": "2025-01-15T10:30:00Z",
            }
        ]

        with patch("src.tools.diagnostics.UniFiClient") as mock_client_class:
            mock_client_class.return_value = create_mock_client([response])

            result = await get_spectrum_scan("site-1", mock_settings)

            assert result["device_id"] == "device-1"
            assert result["frequency_band"] == "2.4"

    @pytest.mark.asyncio
    async def test_get_spectrum_scan_empty(self, mock_settings):
        """Test spectrum scan with empty response."""
        response = {"data": []}

        with patch("src.tools.diagnostics.UniFiClient") as mock_client_class:
            mock_client_class.return_value = create_mock_client([response])

            result = await get_spectrum_scan("site-1", mock_settings)

            assert result == {}

    @pytest.mark.asyncio
    async def test_get_spectrum_scan_invalid_site_id(self, mock_settings):
        """Test validation error for empty site_id."""
        with pytest.raises(ValidationError):
            await get_spectrum_scan("", mock_settings)


class TestListSpectrumInterference:
    @pytest.mark.asyncio
    async def test_list_spectrum_interference_success(self, mock_settings):
        """Test successful retrieval of spectrum interference."""
        response = {
            "data": [
                {
                    "device_id": "device-1",
                    "device_name": "AP-LivingRoom",
                    "frequency_band": "5",
                    "scan_data": [
                        {"channel": 36, "freq": 5180, "util": 80, "noise": -85},
                        {"channel": 40, "freq": 5200, "util": 45, "noise": -92},
                        {"channel": 44, "freq": 5220, "util": 90, "noise": -80},
                    ],
                }
            ]
        }

        with patch("src.tools.diagnostics.UniFiClient") as mock_client_class:
            mock_client_class.return_value = create_mock_client([response])

            result = await list_spectrum_interference("site-1", mock_settings)

            assert isinstance(result, list)
            assert len(result) == 3
            assert result[0]["channel"] == 36
            assert result[2]["channel"] == 44

    @pytest.mark.asyncio
    async def test_list_spectrum_interference_empty(self, mock_settings):
        """Test spectrum interference with empty scan data."""
        response = {"data": []}

        with patch("src.tools.diagnostics.UniFiClient") as mock_client_class:
            mock_client_class.return_value = create_mock_client([response])

            result = await list_spectrum_interference("site-1", mock_settings)

            assert result == []

    @pytest.mark.asyncio
    async def test_list_spectrum_interference_no_scan_data(self, mock_settings):
        """Test spectrum interference with device but no scan_data field."""
        response = {
            "data": [
                {
                    "device_id": "device-1",
                    "device_name": "AP-LivingRoom",
                    "frequency_band": "5",
                }
            ]
        }

        with patch("src.tools.diagnostics.UniFiClient") as mock_client_class:
            mock_client_class.return_value = create_mock_client([response])

            result = await list_spectrum_interference("site-1", mock_settings)

            assert result == []

    @pytest.mark.asyncio
    async def test_list_spectrum_interference_invalid_site_id(self, mock_settings):
        """Test validation error for empty site_id."""
        with pytest.raises(ValidationError):
            await list_spectrum_interference("", mock_settings)
