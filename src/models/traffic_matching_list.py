"""Traffic Matching List data models."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TrafficMatchingListType(str, Enum):
    """Traffic matching list types."""

    PORTS = "PORTS"
    IPV4_ADDRESSES = "IPV4_ADDRESSES"
    IPV6_ADDRESSES = "IPV6_ADDRESSES"


class TrafficMatchingListItem(BaseModel):
    """One entry inside a traffic matching list's `items` array.

    Verified live against Network 10.5.67, GET .../traffic-matching-lists:
    each item is an object — `{"type": "IP_ADDRESS", "value": "10.0.1.25"}"`
    — not a bare string as the list model previously assumed, which made
    every list with any items fail validation.
    """

    type: str = Field(..., description="Item type (e.g. IP_ADDRESS, PORT)")
    value: str = Field(..., description="Item value")

    model_config = ConfigDict(extra="allow")


class TrafficMatchingList(BaseModel):
    """UniFi Traffic Matching List configuration."""

    id: str = Field(..., description="Traffic matching list ID")
    type: TrafficMatchingListType = Field(..., description="List type")
    name: str = Field(..., description="List name")
    items: list[TrafficMatchingListItem] = Field(
        default_factory=list, description="List items (ports, IPs, etc.)"
    )
    site_id: str | None = Field(None, description="Site ID")

    model_config = ConfigDict(
        populate_by_name=True,
        use_enum_values=True,
        json_schema_extra={
            "example": {
                "id": "507f191e810c19729de860ea",
                "type": "PORTS",
                "name": "Common Web Ports",
                "items": [{"type": "PORT", "value": "80"}, {"type": "PORT", "value": "443"}],
            }
        },
    )


class TrafficMatchingListCreate(BaseModel):
    """Request model for creating traffic matching list."""

    type: TrafficMatchingListType = Field(..., description="List type")
    name: str = Field(..., description="List name", min_length=1, max_length=128)
    items: list[str] = Field(..., description="List items (non-empty)", min_length=1)

    model_config = ConfigDict(use_enum_values=True)


class TrafficMatchingListUpdate(BaseModel):
    """Request model for updating traffic matching list."""

    type: TrafficMatchingListType | None = Field(None, description="List type")
    name: str | None = Field(None, description="List name", min_length=1, max_length=128)
    items: list[str] | None = Field(None, description="List items", min_length=1)

    model_config = ConfigDict(use_enum_values=True)
