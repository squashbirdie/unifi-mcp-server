"""Diagnostics data models for network testing and RF analysis."""

from pydantic import BaseModel, ConfigDict, Field


class NetworkReference(BaseModel):
    """Network reference resource showing dependency relationships."""

    id: str | None = Field(None, description="Reference resource ID")
    name: str | None = Field(None, description="Reference resource name")
    type: str | None = Field(None, description="Resource type (e.g., wifi, port_profile, firewall)")
    resource_type: str | None = Field(None, description="Category of referenced resource")
    network_id: str | None = Field(None, description="Network ID being referenced")
    site_id: str | None = Field(None, description="Site identifier")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class SpeedTestResult(BaseModel):
    """Result from a UniFi network speed test."""

    id: str | None = Field(None, description="Speed test result ID")
    status: str | None = Field(None, description="Test status (running, completed, failed)")
    download_speed_mbps: float | None = Field(None, description="Download speed in Mbps")
    upload_speed_mbps: float | None = Field(None, description="Upload speed in Mbps")
    ping_ms: float | None = Field(None, description="Ping latency in milliseconds")
    jitter_ms: float | None = Field(None, description="Jitter in milliseconds")
    timestamp: str | None = Field(None, description="ISO 8601 timestamp of the test")
    server_name: str | None = Field(None, description="Speed test server name")
    server_url: str | None = Field(None, description="Speed test server URL")
    isp: str | None = Field(None, description="Internet service provider name")
    result_url: str | None = Field(None, description="URL to detailed test results")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class SpeedTestHistory(BaseModel):
    """Historical collection of speed test results."""

    count: int = Field(0, description="Total number of results")
    results: list[SpeedTestResult] = Field(
        default_factory=list, description="List of speed test results"
    )
    site_id: str | None = Field(None, description="Site identifier")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class SpectrumScan(BaseModel):
    """RF spectrum scan result from an access point."""

    device_id: str | None = Field(None, description="Device ID that performed the scan")
    device_name: str | None = Field(None, description="Device name")
    frequency_band: str | None = Field(None, description="Frequency band (2.4, 5, or 6 GHz)")
    channel: int | None = Field(None, description="Primary channel number")
    noise_floor_dbm: float | None = Field(None, description="Noise floor in dBm")
    utilization_percent: float | None = Field(None, description="Channel utilization percentage")
    timestamp: str | None = Field(None, description="ISO 8601 timestamp of the scan")
    site_id: str | None = Field(None, description="Site identifier")
    scan_data: list[dict] = Field(default_factory=list, description="Raw per-channel scan data")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class SpectrumInterference(BaseModel):
    """Detected interference from a spectrum scan."""

    channel: int = Field(..., description="WiFi channel number")
    frequency_mhz: float | None = Field(None, description="Center frequency in MHz")
    utilization_percent: float | None = Field(None, description="Channel utilization percentage")
    interference_level: str | None = Field(
        None, description="Interference severity (low, medium, high)"
    )
    interference_type: str | None = Field(None, description="Type of interference detected")
    noise_floor_dbm: float | None = Field(None, description="Noise floor in dBm")
    device_id: str | None = Field(None, description="Device ID that detected the interference")

    model_config = ConfigDict(populate_by_name=True, extra="allow")
