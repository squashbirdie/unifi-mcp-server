"""Traffic Matching List data models.

Rebuilt against the official OpenAPI spec (developer.ui.com/network v10.4.57, fetched
2026-08-26) after discovering the flat ``{"type": str, "value": str}`` item shape this file
previously assumed doesn't match ports at all: ``list_traffic_matching_lists`` against a
live controller (Network 10.5.67) failed Pydantic validation because PORT items carry an
*integer* ``value`` (``{"type": "PORT_NUMBER", "value": 443}``), not a string -- and the
top-level list's own ``type`` (PORTS/IPV4_ADDRESSES/IPV6_ADDRESSES) determines which of
three different item shapes ``items`` actually holds, including two range variants
(``start``/``stop``, no ``value`` at all) this file didn't model at all. See the spec's
"Traffic matching list", "Port matching" and "IPv4/IPv6 matching" schemas.
"""

from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator


class TrafficMatchingListType(str, Enum):
    """Traffic matching list types."""

    PORTS = "PORTS"
    IPV4_ADDRESSES = "IPV4_ADDRESSES"
    IPV6_ADDRESSES = "IPV6_ADDRESSES"


# --- Port matching (list type PORTS) -----------------------------------------------------


class NumberPortMatching(BaseModel):
    """A single port number: ``{"type": "PORT_NUMBER", "value": 443}``."""

    type: Literal["PORT_NUMBER"] = "PORT_NUMBER"
    value: int = Field(..., ge=1, le=65535, description="Port number")

    model_config = ConfigDict(extra="allow")


class NumberRangePortMatching(BaseModel):
    """An inclusive port range: ``{"type": "PORT_NUMBER_RANGE", "start": 8000, "stop": 8100}``."""

    type: Literal["PORT_NUMBER_RANGE"] = "PORT_NUMBER_RANGE"
    start: int = Field(..., ge=1, le=65535)
    stop: int = Field(..., ge=1, le=65535)

    model_config = ConfigDict(extra="allow")


PortMatching = Annotated[
    NumberPortMatching | NumberRangePortMatching,
    Field(discriminator="type"),
]

# --- IPv4 matching (list type IPV4_ADDRESSES) --------------------------------------------


class AddressIPv4Matching(BaseModel):
    type: Literal["IP_ADDRESS"] = "IP_ADDRESS"
    value: str = Field(..., description="IPv4 address, e.g. '192.168.1.5'")

    model_config = ConfigDict(extra="allow")


class AddressRangeIPv4Matching(BaseModel):
    type: Literal["IP_ADDRESS_RANGE"] = "IP_ADDRESS_RANGE"
    start: str = Field(..., description="IPv4 start address")
    stop: str = Field(..., description="IPv4 stop address")

    model_config = ConfigDict(extra="allow")


class SubnetIPv4Matching(BaseModel):
    type: Literal["SUBNET"] = "SUBNET"
    value: str = Field(..., description="IPv4 subnet in CIDR notation, e.g. '192.168.1.0/24'")

    model_config = ConfigDict(extra="allow")


IPv4Matching = Annotated[
    AddressIPv4Matching | AddressRangeIPv4Matching | SubnetIPv4Matching,
    Field(discriminator="type"),
]

# --- IPv6 matching (list type IPV6_ADDRESSES) ------------------------------------------
# Unlike IPv4, the spec documents no IP_ADDRESS_RANGE variant for IPv6 - only a single
# address and a subnet.


class AddressIPv6Matching(BaseModel):
    type: Literal["IP_ADDRESS"] = "IP_ADDRESS"
    value: str = Field(..., description="IPv6 address")

    model_config = ConfigDict(extra="allow")


class SubnetIPv6Matching(BaseModel):
    type: Literal["SUBNET"] = "SUBNET"
    value: str = Field(..., description="IPv6 subnet in CIDR notation")

    model_config = ConfigDict(extra="allow")


IPv6Matching = Annotated[
    AddressIPv6Matching | SubnetIPv6Matching,
    Field(discriminator="type"),
]

# --- Top-level list, discriminated by its OWN `type` (not the item type) ---------------


class PortTrafficMatchingList(BaseModel):
    type: Literal["PORTS"] = "PORTS"
    id: str = Field(..., description="Traffic matching list ID")
    name: str = Field(..., description="List name")
    items: list[PortMatching] = Field(default_factory=list)
    site_id: str | None = Field(None, description="Site ID")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class IPv4TrafficMatchingList(BaseModel):
    type: Literal["IPV4_ADDRESSES"] = "IPV4_ADDRESSES"
    id: str = Field(..., description="Traffic matching list ID")
    name: str = Field(..., description="List name")
    items: list[IPv4Matching] = Field(default_factory=list)
    site_id: str | None = Field(None, description="Site ID")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class IPv6TrafficMatchingList(BaseModel):
    type: Literal["IPV6_ADDRESSES"] = "IPV6_ADDRESSES"
    id: str = Field(..., description="Traffic matching list ID")
    name: str = Field(..., description="List name")
    items: list[IPv6Matching] = Field(default_factory=list)
    site_id: str | None = Field(None, description="Site ID")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


TrafficMatchingList = Annotated[
    PortTrafficMatchingList | IPv4TrafficMatchingList | IPv6TrafficMatchingList,
    Field(discriminator="type"),
]

_TrafficMatchingListUnion = (
    PortTrafficMatchingList | IPv4TrafficMatchingList | IPv6TrafficMatchingList
)
_traffic_matching_list_adapter: TypeAdapter[_TrafficMatchingListUnion] = TypeAdapter(
    TrafficMatchingList
)

_ITEM_ADAPTERS: dict[str, TypeAdapter[Any]] = {
    "PORTS": TypeAdapter(PortMatching),
    "IPV4_ADDRESSES": TypeAdapter(IPv4Matching),
    "IPV6_ADDRESSES": TypeAdapter(IPv6Matching),
}


def parse_traffic_matching_list(data: dict[str, Any]) -> _TrafficMatchingListUnion:
    """Validate and parse one traffic matching list response object.

    Use this instead of calling ``PortTrafficMatchingList``/etc. directly - the top-level
    shape is a discriminated union on ``type``, which pydantic can only resolve through a
    ``TypeAdapter``, not a plain constructor call.
    """
    return _traffic_matching_list_adapter.validate_python(data)


class TrafficMatchingListCreate(BaseModel):
    """Request model for creating a traffic matching list.

    ``items`` must already be shaped to match ``type`` - build them with
    ``tools.traffic_matching_lists._normalise_items``, don't hand-construct dicts. Each
    item is validated against the real per-type item schema before being sent.
    """

    type: TrafficMatchingListType = Field(..., description="List type")
    name: str = Field(..., description="List name", min_length=1, max_length=128)
    items: list[dict[str, Any]] = Field(
        ..., description="List items (shape depends on `type`)", min_length=1
    )

    model_config = ConfigDict(use_enum_values=True)

    @model_validator(mode="after")
    def _validate_items(self) -> "TrafficMatchingListCreate":
        adapter = _ITEM_ADAPTERS[self.type]
        self.items = [adapter.validate_python(item).model_dump() for item in self.items]
        return self


class TrafficMatchingListUpdate(BaseModel):
    """Request model for updating a traffic matching list. See ``TrafficMatchingListCreate``."""

    type: TrafficMatchingListType | None = Field(None, description="List type")
    name: str | None = Field(None, description="List name", min_length=1, max_length=128)
    items: list[dict[str, Any]] | None = Field(
        None, description="List items (shape depends on `type`)", min_length=1
    )

    model_config = ConfigDict(use_enum_values=True)

    @model_validator(mode="after")
    def _validate_items(self) -> "TrafficMatchingListUpdate":
        if self.items is not None and self.type is not None:
            adapter = _ITEM_ADAPTERS[self.type]
            self.items = [adapter.validate_python(item).model_dump() for item in self.items]
        return self
