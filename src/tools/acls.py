"""Access Control List (ACL) management tools."""

from typing import Any

from ..api.client import UniFiClient
from ..config import Settings
from ..models.acl import parse_acl_rule
from ..utils import audit_action, get_logger, sanitize_log_message, validate_confirmation

logger = get_logger(__name__)

# The UniFi integration API accepts only these values on ACL rules.
_VALID_ACTIONS = ("ALLOW", "BLOCK")
_VALID_TYPES = ("IPV4", "MAC")
_VALID_PROTOCOLS = ("TCP", "UDP")


def _ensure_cloud_api(settings: Settings) -> None:
    """No-op retained for call-site compatibility.

    ACL rules were long believed cloud-only; that stopped being true once the
    Integration API shipped locally (GA on Network App >= 9.3 — see
    Settings.get_integration_path's LOCAL branch, which already targets
    /proxy/network/integration/v1/...). Verified live against Network 10.5.67:
    GET .../acl-rules returns 200. Kept as a function (rather than deleting
    every call site) in case a future controller version reintroduces a real
    split between read and write support here.
    """
    return


def _normalise_action(action: str) -> str:
    upper = action.upper()
    if upper not in _VALID_ACTIONS:
        raise ValueError(
            f"Invalid action '{action}'. UniFi integration API accepts only {_VALID_ACTIONS}."
        )
    return upper


def _normalise_type(type_value: str) -> str:
    upper = type_value.upper()
    if upper not in _VALID_TYPES:
        raise ValueError(
            f"Invalid type '{type_value}'. UniFi integration API accepts only {_VALID_TYPES}."
        )
    return upper


def _normalise_protocol_filter(protocols: list[str] | None) -> list[str] | None:
    if protocols is None:
        return None
    upper = [p.upper() for p in protocols]
    invalid = [p for p in upper if p not in _VALID_PROTOCOLS]
    if invalid:
        raise ValueError(f"Invalid protocol(s) {invalid}. Must be a subset of {_VALID_PROTOCOLS}.")
    return upper


def _build_ip_endpoint(
    *,
    network_ids: list[str] | None,
    ports: list[int] | None,
    ip_addresses_or_subnets: list[str] | None,
    port_filter: list[int] | None,
    role: str,
) -> dict[str, Any] | None:
    """Build a `sourceFilter`/`destinationFilter` object for an IPV4 ACL rule.

    The integration API's "IP ACL rule endpoint" is a discriminated union on `type`:

    * `NETWORKS` — match by VLAN membership (`network_ids`), optionally narrowed with
      `port_filter`.
    * `PORTS` — match by port only, irrespective of network or IP (`ports`).
    * `IP_ADDRESSES_OR_SUBNETS` — match by literal IP/CIDR (`ip_addresses_or_subnets`),
      optionally narrowed with `port_filter`.

    Exactly one of `network_ids`, `ports`, `ip_addresses_or_subnets` selects the variant;
    passing more than one, or none while `port_filter` alone is set, is an error — the
    caller must pick a variant. Returns `None` when the caller wants no filter on this side
    at all (matches any source/destination).
    """
    provided = [
        name
        for name, value in (
            ("network_ids", network_ids),
            ("ports", ports),
            ("ip_addresses_or_subnets", ip_addresses_or_subnets),
        )
        if value
    ]
    if not provided:
        if port_filter:
            raise ValueError(
                f"{role}_port_filter was given without {role}_network_ids, {role}_ports, "
                f"or {role}_ip_addresses_or_subnets — pick which endpoint variant it narrows."
            )
        return None
    if len(provided) > 1:
        raise ValueError(
            f"{role} filter is ambiguous: got {provided}, but the API accepts exactly one "
            "of network_ids, ports, or ip_addresses_or_subnets per endpoint."
        )

    if network_ids:
        return {"type": "NETWORKS", "networkIds": network_ids, "portFilter": port_filter}
    if ports:
        if port_filter:
            raise ValueError(f"{role}_ports already IS the port filter — don't also pass port_filter.")
        return {"type": "PORTS", "portFilter": ports}
    return {
        "type": "IP_ADDRESSES_OR_SUBNETS",
        "ipAddressesOrSubnets": ip_addresses_or_subnets,
        "portFilter": port_filter,
    }


def _build_mac_endpoint(
    *, mac_addresses: list[str] | None, prefix_length: int | None, role: str
) -> dict[str, Any] | None:
    """Build a `sourceFilter`/`destinationFilter` object for a MAC ACL rule. Only one
    endpoint variant (`MAC_ADDRESSES`) is documented."""
    if not mac_addresses:
        if prefix_length is not None:
            raise ValueError(f"{role}_mac_prefix_length was given without {role}_mac_addresses.")
        return None
    return {
        "type": "MAC_ADDRESSES",
        "macAddresses": mac_addresses,
        "prefixLength": prefix_length,
    }


async def list_acl_rules(
    site_id: str,
    settings: Settings,
    limit: int | None = None,
    offset: int | None = None,
    filter_expr: str | None = None,
) -> list[dict]:
    """List all ACL rules for a site.

    Args:
        site_id: Site identifier
        settings: Application settings
        limit: Maximum number of results
        offset: Starting position
        filter_expr: Filter expression

    Returns:
        List of ACL rules
    """
    _ensure_cloud_api(settings)
    async with UniFiClient(settings) as client:
        logger.info(sanitize_log_message(f"Listing ACL rules for site {site_id}"))

        if not client.is_authenticated:
            await client.authenticate()

        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        if filter_expr:
            params["filter"] = filter_expr

        resolved_site_id = await client.resolve_site_id(site_id)
        response = await client.get(
            settings.get_integration_path(f"sites/{resolved_site_id}/acl-rules"),
            params=params,
        )
        data = response if isinstance(response, list) else response.get("data", [])

        return [parse_acl_rule(rule).model_dump() for rule in data]


async def get_acl_rule(site_id: str, acl_rule_id: str, settings: Settings) -> dict:
    """Get details for a specific ACL rule.

    Args:
        site_id: Site identifier
        acl_rule_id: ACL rule identifier
        settings: Application settings

    Returns:
        ACL rule details
    """
    _ensure_cloud_api(settings)
    async with UniFiClient(settings) as client:
        logger.info(sanitize_log_message(f"Getting ACL rule {acl_rule_id} for site {site_id}"))

        if not client.is_authenticated:
            await client.authenticate()

        resolved_site_id = await client.resolve_site_id(site_id)
        response = await client.get(
            settings.get_integration_path(f"sites/{resolved_site_id}/acl-rules/{acl_rule_id}")
        )
        data = response.get("data", response)

        return parse_acl_rule(data).model_dump()


async def create_acl_rule(
    site_id: str,
    name: str,
    action: str,
    settings: Settings,
    type: str = "IPV4",
    enabled: bool = True,
    description: str | None = None,
    network_id_filter: str | None = None,
    source_network_ids: list[str] | None = None,
    source_ports: list[int] | None = None,
    source_ip_addresses_or_subnets: list[str] | None = None,
    source_port_filter: list[int] | None = None,
    source_mac_addresses: list[str] | None = None,
    source_mac_prefix_length: int | None = None,
    destination_network_ids: list[str] | None = None,
    destination_ports: list[int] | None = None,
    destination_ip_addresses_or_subnets: list[str] | None = None,
    destination_port_filter: list[int] | None = None,
    destination_mac_addresses: list[str] | None = None,
    destination_mac_prefix_length: int | None = None,
    protocol_filter: list[str] | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict:
    """Create a new ACL rule.

    Omitting every source/destination parameter creates an unfiltered rule that matches
    ALL traffic of the given `type` — almost never what you want; specify a source and/or
    destination filter to scope it.

    Args:
        site_id: Site identifier
        name: Rule name
        action: ALLOW or BLOCK (case-insensitive). DROP/REJECT/DENY are not
            accepted by the integration API.
        settings: Application settings
        type: Rule type — IPV4 or MAC. Defaults to IPV4.
        enabled: Whether the rule is enabled (defaults to True)
        description: Optional rule description.
        network_id_filter: REQUIRED when type='MAC' — the network this rule applies to.
            Not used for type='IPV4'.
        source_network_ids / destination_network_ids: type='IPV4' only. Match traffic by
            VLAN membership. Mutually exclusive with the `*_ports` and
            `*_ip_addresses_or_subnets` params on the same side.
        source_ports / destination_ports: type='IPV4' only. Match traffic by port alone,
            irrespective of network or IP.
        source_ip_addresses_or_subnets / destination_ip_addresses_or_subnets: type='IPV4'
            only. Match traffic by literal IP address or CIDR subnet.
        source_port_filter / destination_port_filter: type='IPV4' only. Narrows a
            `*_network_ids` or `*_ip_addresses_or_subnets` filter to specific ports; do not
            pass alongside `*_ports` (which already IS the port filter).
        source_mac_addresses / destination_mac_addresses: type='MAC' only. Match traffic by
            literal MAC address.
        source_mac_prefix_length / destination_mac_prefix_length: type='MAC' only. Narrows
            a MAC match to a prefix (OUI-style) instead of the full address.
        protocol_filter: type='IPV4' only. Subset of ["TCP", "UDP"]; omit to match all
            protocols.
        confirm: Confirmation flag (required)
        dry_run: If True, validate but don't execute

    Returns:
        Created ACL rule
    """
    validate_confirmation(confirm, "create ACL rule", dry_run)

    _ensure_cloud_api(settings)
    normalised_action = _normalise_action(action)
    normalised_type = _normalise_type(type)

    payload: dict[str, Any] = {
        "name": name,
        "enabled": enabled,
        "action": normalised_action,
        "type": normalised_type,
    }
    if description is not None:
        payload["description"] = description

    if normalised_type == "MAC":
        if not network_id_filter:
            raise ValueError("network_id_filter is required when type='MAC'.")
        payload["networkIdFilter"] = network_id_filter
        source_filter = _build_mac_endpoint(
            mac_addresses=source_mac_addresses,
            prefix_length=source_mac_prefix_length,
            role="source",
        )
        destination_filter = _build_mac_endpoint(
            mac_addresses=destination_mac_addresses,
            prefix_length=destination_mac_prefix_length,
            role="destination",
        )
    else:  # IPV4
        source_filter = _build_ip_endpoint(
            network_ids=source_network_ids,
            ports=source_ports,
            ip_addresses_or_subnets=source_ip_addresses_or_subnets,
            port_filter=source_port_filter,
            role="source",
        )
        destination_filter = _build_ip_endpoint(
            network_ids=destination_network_ids,
            ports=destination_ports,
            ip_addresses_or_subnets=destination_ip_addresses_or_subnets,
            port_filter=destination_port_filter,
            role="destination",
        )
        normalised_protocols = _normalise_protocol_filter(protocol_filter)
        if normalised_protocols is not None:
            payload["protocolFilter"] = normalised_protocols

    if source_filter is not None:
        payload["sourceFilter"] = source_filter
    if destination_filter is not None:
        payload["destinationFilter"] = destination_filter

    if dry_run:
        logger.info(
            sanitize_log_message(f"[DRY RUN] Would create ACL rule '{name}' for site {site_id}")
        )
        return {"dry_run": True, "payload": payload}

    async with UniFiClient(settings) as client:
        logger.info(sanitize_log_message(f"Creating ACL rule '{name}' for site {site_id}"))

        if not client.is_authenticated:
            await client.authenticate()

        resolved_site_id = await client.resolve_site_id(site_id)
        response = await client.post(
            settings.get_integration_path(f"sites/{resolved_site_id}/acl-rules"),
            json_data=payload,
        )
        data = response.get("data", response)

        # Audit the action
        await audit_action(
            settings,
            action_type="create_acl_rule",
            resource_type="acl_rule",
            resource_id=data.get("id", "unknown"),
            site_id=site_id,
            details={"name": name, "action": normalised_action, "type": normalised_type},
        )

        return parse_acl_rule(data).model_dump()


async def update_acl_rule(
    site_id: str,
    acl_rule_id: str,
    settings: Settings,
    name: str | None = None,
    action: str | None = None,
    type: str | None = None,
    enabled: bool | None = None,
    description: str | None = None,
    network_id_filter: str | None = None,
    source_network_ids: list[str] | None = None,
    source_ports: list[int] | None = None,
    source_ip_addresses_or_subnets: list[str] | None = None,
    source_port_filter: list[int] | None = None,
    source_mac_addresses: list[str] | None = None,
    source_mac_prefix_length: int | None = None,
    destination_network_ids: list[str] | None = None,
    destination_ports: list[int] | None = None,
    destination_ip_addresses_or_subnets: list[str] | None = None,
    destination_port_filter: list[int] | None = None,
    destination_mac_addresses: list[str] | None = None,
    destination_mac_prefix_length: int | None = None,
    protocol_filter: list[str] | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict:
    """Update an existing ACL rule. Only fields you pass are sent (partial update).

    `type` must be given whenever you also pass any source/destination filter — the
    integration API needs it to know which endpoint schema (IP vs MAC) applies, and this
    tool has no way to look up the rule's existing type without an extra round trip.
    `index` is intentionally not a parameter: the API's own update schema marks it
    deprecated in favour of a dedicated ACL rule reordering endpoint.

    Args:
        site_id: Site identifier
        acl_rule_id: ACL rule identifier
        settings: Application settings
        name: Rule name
        action: ALLOW or BLOCK (case-insensitive)
        type: Rule type — IPV4 or MAC. Required if any filter parameter below is passed.
        enabled: Whether the rule is enabled
        description: Rule description
        network_id_filter: type='MAC' only — the network this rule applies to.
        source_network_ids / destination_network_ids: type='IPV4' only.
        source_ports / destination_ports: type='IPV4' only.
        source_ip_addresses_or_subnets / destination_ip_addresses_or_subnets: type='IPV4' only.
        source_port_filter / destination_port_filter: type='IPV4' only.
        source_mac_addresses / destination_mac_addresses: type='MAC' only.
        source_mac_prefix_length / destination_mac_prefix_length: type='MAC' only.
        protocol_filter: type='IPV4' only. Subset of ["TCP", "UDP"].
        confirm: Confirmation flag (required)
        dry_run: If True, validate but don't execute

    Returns:
        Updated ACL rule
    """
    validate_confirmation(confirm, "update ACL rule", dry_run)

    _ensure_cloud_api(settings)
    normalised_action = _normalise_action(action) if action is not None else None
    normalised_type = _normalise_type(type) if type is not None else None

    filter_params_given = any(
        [
            network_id_filter,
            source_network_ids,
            source_ports,
            source_ip_addresses_or_subnets,
            source_port_filter,
            source_mac_addresses,
            source_mac_prefix_length,
            destination_network_ids,
            destination_ports,
            destination_ip_addresses_or_subnets,
            destination_port_filter,
            destination_mac_addresses,
            destination_mac_prefix_length,
            protocol_filter,
        ]
    )
    if filter_params_given and normalised_type is None:
        raise ValueError(
            "type must be given when updating any source/destination filter — this tool "
            "cannot infer whether the existing rule is IPV4 or MAC without an extra fetch."
        )

    payload: dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if normalised_action is not None:
        payload["action"] = normalised_action
    if normalised_type is not None:
        payload["type"] = normalised_type
    if enabled is not None:
        payload["enabled"] = enabled
    if description is not None:
        payload["description"] = description

    if normalised_type == "MAC":
        if network_id_filter is not None:
            payload["networkIdFilter"] = network_id_filter
        source_filter = _build_mac_endpoint(
            mac_addresses=source_mac_addresses,
            prefix_length=source_mac_prefix_length,
            role="source",
        )
        destination_filter = _build_mac_endpoint(
            mac_addresses=destination_mac_addresses,
            prefix_length=destination_mac_prefix_length,
            role="destination",
        )
    elif normalised_type == "IPV4":
        source_filter = _build_ip_endpoint(
            network_ids=source_network_ids,
            ports=source_ports,
            ip_addresses_or_subnets=source_ip_addresses_or_subnets,
            port_filter=source_port_filter,
            role="source",
        )
        destination_filter = _build_ip_endpoint(
            network_ids=destination_network_ids,
            ports=destination_ports,
            ip_addresses_or_subnets=destination_ip_addresses_or_subnets,
            port_filter=destination_port_filter,
            role="destination",
        )
        normalised_protocols = _normalise_protocol_filter(protocol_filter)
        if normalised_protocols is not None:
            payload["protocolFilter"] = normalised_protocols
    else:
        source_filter = None
        destination_filter = None

    if source_filter is not None:
        payload["sourceFilter"] = source_filter
    if destination_filter is not None:
        payload["destinationFilter"] = destination_filter

    async with UniFiClient(settings) as client:
        logger.info(sanitize_log_message(f"Updating ACL rule {acl_rule_id} for site {site_id}"))

        if not client.is_authenticated:
            await client.authenticate()

        if dry_run:
            logger.info(
                sanitize_log_message(
                    f"[DRY RUN] Would update ACL rule {acl_rule_id} for site {site_id}"
                )
            )
            return {"dry_run": True, "payload": payload}

        resolved_site_id = await client.resolve_site_id(site_id)
        response = await client.put(
            settings.get_integration_path(f"sites/{resolved_site_id}/acl-rules/{acl_rule_id}"),
            json_data=payload,
        )
        if isinstance(response, list):
            data = response[0] if response else {}
        else:
            _raw = response.get("data", response)
            data = _raw[0] if isinstance(_raw, list) else _raw

        # Audit the action
        await audit_action(
            settings,
            action_type="update_acl_rule",
            resource_type="acl_rule",
            resource_id=acl_rule_id,
            site_id=site_id,
            details=payload,
        )

        return parse_acl_rule(data).model_dump()


async def delete_acl_rule(
    site_id: str,
    acl_rule_id: str,
    settings: Settings,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict:
    """Delete an ACL rule.

    Args:
        site_id: Site identifier
        acl_rule_id: ACL rule identifier
        settings: Application settings
        confirm: Confirmation flag (required)
        dry_run: If True, validate but don't execute

    Returns:
        Deletion status
    """
    validate_confirmation(confirm, "delete ACL rule", dry_run)

    _ensure_cloud_api(settings)
    async with UniFiClient(settings) as client:
        logger.info(sanitize_log_message(f"Deleting ACL rule {acl_rule_id} for site {site_id}"))

        if not client.is_authenticated:
            await client.authenticate()

        if dry_run:
            logger.info(sanitize_log_message(f"[DRY RUN] Would delete ACL rule {acl_rule_id}"))
            return {"dry_run": True, "acl_rule_id": acl_rule_id}

        resolved_site_id = await client.resolve_site_id(site_id)
        await client.delete(
            settings.get_integration_path(f"sites/{resolved_site_id}/acl-rules/{acl_rule_id}")
        )

        # Audit the action
        await audit_action(
            settings,
            action_type="delete_acl_rule",
            resource_type="acl_rule",
            resource_id=acl_rule_id,
            site_id=site_id,
            details={},
        )

        return {"success": True, "message": f"ACL rule {acl_rule_id} deleted successfully"}
