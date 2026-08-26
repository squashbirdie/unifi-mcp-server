"""Access Control List (ACL) models.

Rebuilt against the official OpenAPI spec (developer.ui.com/network v10.4.57, fetched
2026-08-26). The previous model was an entirely guessed flat shape (``source_type``,
``dst_port``, ``source_network``, ...) that does not exist in the real API at all - it
only ever "worked" because every one of those fields was Optional and the one production
controller checked against had zero ACL rules to validate against. The real shape is a
discriminated union on ``type`` (``IPV4`` / ``MAC``), each carrying ``sourceFilter``/
``destinationFilter`` objects that are themselves discriminated unions - see the spec's
"ACL rule", "IP ACL rule endpoint" and "MAC ACL rule endpoint" schemas.

This also means the previous claim (in ``tools/acls.py``) that "the integration API
accepts only ``{name, action, type, enabled}``" on create was a symptom of the wrong field
names being tried (``source_network`` etc.), not an actual API limitation -
``sourceFilter``/``destinationFilter`` are real, documented, and required for a rule to
filter anything narrower than "all traffic".
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class EntityMetadata(BaseModel):
    """The ``metadata`` envelope on every ACL rule. ``origin`` (``USER_DEFINED`` or
    ``DERIVED``) is the only field modelled explicitly - the spec's inheritance chain for
    USER_DEFINED metadata references several unrelated schemas (including one literally
    named "Site-to-site VPN tunnel metadata"), which reads as a spec-generation artifact
    rather than a real ACL-rule field set. Extras pass through unmodeled rather than
    guessing at a schema that may not be real."""

    origin: str = Field(..., description="'USER_DEFINED' or 'DERIVED'")

    model_config = ConfigDict(extra="allow")


class ACLRuleDeviceFilter(BaseModel):
    """Which switch-capable devices enforce the rule. ``device_ids`` is only present for
    the one documented variant (``DEVICES``); kept optional so an undocumented variant
    degrades to a plain passthrough object instead of a validation error."""

    type: str = Field(..., description="Filter type, e.g. 'DEVICES'")
    device_ids: list[str] | None = Field(None, alias="deviceIds")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


# --- IP ACL rule source/destination filters ----------------------------------------------


class IPACLRuleNetworkEndpoint(BaseModel):
    """Match traffic by VLAN/network membership, optionally narrowed to specific ports."""

    type: Literal["NETWORKS"] = "NETWORKS"
    network_ids: list[str] = Field(..., alias="networkIds")
    port_filter: list[int] | None = Field(None, alias="portFilter")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class IPACLRulePortEndpoint(BaseModel):
    """Match traffic by port only, irrespective of network or IP."""

    type: Literal["PORTS"] = "PORTS"
    port_filter: list[int] = Field(..., alias="portFilter")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class IPACLRuleSubnetEndpoint(BaseModel):
    """Match traffic by literal IP address or CIDR subnet, optionally narrowed to
    specific ports."""

    type: Literal["IP_ADDRESSES_OR_SUBNETS"] = "IP_ADDRESSES_OR_SUBNETS"
    ip_addresses_or_subnets: list[str] = Field(..., alias="ipAddressesOrSubnets")
    port_filter: list[int] | None = Field(None, alias="portFilter")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


IPACLRuleEndpoint = Annotated[
    IPACLRuleNetworkEndpoint | IPACLRulePortEndpoint | IPACLRuleSubnetEndpoint,
    Field(discriminator="type"),
]

_ip_endpoint_adapter: TypeAdapter = TypeAdapter(IPACLRuleEndpoint)

# --- MAC ACL rule source/destination filters ----------------------------------------------
# Only one variant is documented (MAC_ADDRESSES); no union needed.


class MACACLRuleEndpoint(BaseModel):
    """Match traffic by literal MAC address, optionally a prefix (OUI-style match)."""

    type: Literal["MAC_ADDRESSES"] = "MAC_ADDRESSES"
    mac_addresses: list[str] = Field(..., alias="macAddresses")
    prefix_length: int | None = Field(None, alias="prefixLength")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


_mac_endpoint_adapter: TypeAdapter = TypeAdapter(MACACLRuleEndpoint)

# --- The two ACL rule shapes ----------------------------------------------------------------


class IPACLRule(BaseModel):
    """An ACL rule with ``type: "IPV4"``."""

    type: Literal["IPV4"] = "IPV4"
    id: str = Field(..., description="ACL rule ID (uuid)")
    index: int = Field(..., description="Priority index; lower = higher priority")
    name: str
    enabled: bool
    action: Literal["ALLOW", "BLOCK"]
    description: str | None = None
    metadata: EntityMetadata
    enforcing_device_filter: ACLRuleDeviceFilter | None = Field(
        None, alias="enforcingDeviceFilter"
    )
    source_filter: IPACLRuleEndpoint | None = Field(None, alias="sourceFilter")
    destination_filter: IPACLRuleEndpoint | None = Field(None, alias="destinationFilter")
    protocol_filter: list[Literal["TCP", "UDP"]] | None = Field(None, alias="protocolFilter")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class MACACLRule(BaseModel):
    """An ACL rule with ``type: "MAC"``."""

    type: Literal["MAC"] = "MAC"
    id: str = Field(..., description="ACL rule ID (uuid)")
    index: int = Field(..., description="Priority index; lower = higher priority")
    name: str
    enabled: bool
    action: Literal["ALLOW", "BLOCK"]
    description: str | None = None
    metadata: EntityMetadata
    network_id_filter: str = Field(..., alias="networkIdFilter")
    enforcing_device_filter: ACLRuleDeviceFilter | None = Field(
        None, alias="enforcingDeviceFilter"
    )
    source_filter: MACACLRuleEndpoint | None = Field(None, alias="sourceFilter")
    destination_filter: MACACLRuleEndpoint | None = Field(None, alias="destinationFilter")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


ACLRuleUnion = Annotated[IPACLRule | MACACLRule, Field(discriminator="type")]

_acl_rule_adapter: TypeAdapter[IPACLRule | MACACLRule] = TypeAdapter(ACLRuleUnion)


def parse_acl_rule(data: dict[str, Any]) -> IPACLRule | MACACLRule:
    """Validate and parse one ACL rule response object.

    Use this instead of calling ``IPACLRule``/``MACACLRule`` directly - the top-level
    shape is a discriminated union on ``type``, which pydantic can only resolve through a
    ``TypeAdapter``.
    """
    return _acl_rule_adapter.validate_python(data)
