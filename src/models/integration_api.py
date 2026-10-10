"""Models for responses of the UniFi Network Integration API (v1).

Subset of enuno/unifi-mcp-server ``src/models/integration_api.py``: only the device model is
carried here, because ``get_device_details`` needs it. Keep the class body identical to
upstream so later cherry-picks of that file apply cleanly.
"""

from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class IntegrationDevice(BaseModel):
    """Device as returned by the integration API /v1/sites/{siteId}/devices."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str = Field(
        ...,
        validation_alias=AliasChoices("id", "_id"),
        description="Device UUID (accepts the legacy ``_id`` key as well)",
    )
    mac_address: str | None = Field(None, alias="macAddress", description="Device MAC address")
    ip_address: str | None = Field(None, alias="ipAddress", description="Device IP address")
    name: str | None = Field(None, description="Device name")
    model: str | None = Field(None, description="Device model string")
    state: str | None = Field(None, description="Device state (e.g., ONLINE, OFFLINE)")
    supported: bool | None = Field(None, description="Whether the device is supported")
    firmware_version: str | None = Field(
        None, alias="firmwareVersion", description="Current firmware version"
    )
    firmware_updatable: bool | None = Field(
        None, alias="firmwareUpdatable", description="Whether firmware can be updated"
    )
    # ``features`` and ``interfaces`` come in two shapes. The detail endpoint
    # sends objects (``features.switching`` / ``features.accessPoint``,
    # ``interfaces.ports[...]`` / ``interfaces.radios[...]``); the list endpoint
    # may send just the names (``["switching", "accessPoint"]``,
    # ``["ports", "radios"]``), e.g. on a UDR7 (issue #170). Keep either verbatim.
    features: dict[str, Any] | list[str] | None = Field(
        None, description="Per-capability feature details, or capability names"
    )
    interfaces: dict[str, Any] | list[str] | None = Field(
        None, description="Ports and radios reported by the device, or interface names"
    )
