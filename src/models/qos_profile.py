"""Traffic route data models.

Note: QoSProfile, ProAVTemplate, SmartQueueConfig and related models were
removed because they backed tools using non-existent API endpoints
(rest/qosprofile, rest/wanconf). See src/tools/qos.py docstring for details.
"""

from enum import Enum

from pydantic import BaseModel, Field


class RouteAction(str, Enum):
    """Traffic route action types."""

    ALLOW = "allow"  # Allow traffic
    DENY = "deny"  # Deny traffic
    MARK = "mark"  # Mark with DSCP
    SHAPE = "shape"  # Shape to rate


class MatchCriteria(BaseModel):
    """Traffic matching criteria for routing policies."""

    source_ip: str | None = Field(None, description="Source IP address or CIDR")
    destination_ip: str | None = Field(None, description="Destination IP address or CIDR")
    source_port: int | None = Field(None, ge=1, le=65535, description="Source port")
    destination_port: int | None = Field(None, ge=1, le=65535, description="Destination port")
    protocol: str | None = Field(None, description="Protocol (tcp, udp, icmp, all)")
    vlan_id: int | None = Field(None, ge=1, le=4094, description="VLAN ID")

    class Config:
        """Pydantic configuration."""

        use_enum_values = True


class RouteSchedule(BaseModel):
    """Time-based routing schedule."""

    enabled: bool = Field(False, description="Enable time-based schedule")
    days: list[str] = Field(
        default_factory=list, description="Days active (mon, tue, wed, thu, fri, sat, sun)"
    )
    start_time: str | None = Field(None, description="Start time (HH:MM format)")
    end_time: str | None = Field(None, description="End time (HH:MM format)")

    class Config:
        """Pydantic configuration."""

        use_enum_values = True


class TrafficRoute(BaseModel):
    """Policy-based traffic routing configuration."""

    id: str = Field(alias="_id", description="Route ID")
    name: str = Field(..., description="Route name")
    description: str | None = Field(None, description="Route description")
    action: RouteAction = Field(..., description="Route action")
    enabled: bool = Field(True, description="Route enabled")

    # Traffic matching
    match_criteria: MatchCriteria = Field(..., description="Traffic matching criteria")

    # QoS settings
    dscp_marking: int | None = Field(None, ge=0, le=63, description="DSCP value to mark")
    bandwidth_limit_kbps: int | None = Field(None, ge=0, description="Bandwidth limit in kbps")

    # Scheduling
    schedule: RouteSchedule | None = Field(None, description="Time-based schedule")

    # Priority
    priority: int = Field(
        default=100, ge=1, le=1000, description="Route priority (lower = higher priority)"
    )

    # State
    site_id: str | None = Field(None, description="Site ID")

    class Config:
        """Pydantic configuration."""

        populate_by_name = True
        use_enum_values = True
