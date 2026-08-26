"""Switching data models for Switch Stacks, MC-LAG Domains, and LAGs."""

from pydantic import BaseModel, ConfigDict, Field


class LagMember(BaseModel):
    """LAG member representing a device and its participating ports."""

    device_id: str = Field(..., description="Device UUID", alias="deviceId")
    port_idxs: list[int] = Field(..., description="Participating port indices", alias="portIdxs")

    model_config = ConfigDict(populate_by_name=True)


class SwitchStack(BaseModel):
    """UniFi Switch Stack configuration."""

    id: str = Field(..., description="Switch stack ID")
    name: str = Field(..., description="Switch stack name")
    members: list[dict] = Field(default_factory=list, description="Stack members")
    lags: list[dict] = Field(default_factory=list, description="LAGs in the stack")
    metadata: dict | None = Field(None, description="Metadata including origin")

    model_config = ConfigDict(populate_by_name=True)


class MclagDomain(BaseModel):
    """UniFi MC-LAG Domain configuration."""

    id: str = Field(..., description="MC-LAG domain ID")
    name: str = Field(..., description="MC-LAG domain name")
    peers: list[dict] = Field(default_factory=list, description="Domain peers")
    lags: list[dict] = Field(default_factory=list, description="LAGs in the domain")
    metadata: dict | None = Field(None, description="Metadata including origin")

    model_config = ConfigDict(populate_by_name=True)


class Lag(BaseModel):
    """UniFi Link Aggregation Group (LAG) configuration."""

    type: str = Field(..., description="LAG type: LOCAL, SWITCH_STACK, or MULTI_CHASSIS")
    id: str = Field(..., description="LAG ID")
    members: list[LagMember] = Field(default_factory=list, description="LAG members")
    switch_stack_id: str | None = Field(
        None, description="Associated switch stack ID", alias="switchStackId"
    )

    model_config = ConfigDict(populate_by_name=True)
