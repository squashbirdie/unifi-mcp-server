"""Network configuration MCP tools."""

from typing import Any

from ..api import UniFiClient
from ..config import Settings
from ..utils import (
    APIError,
    ResourceNotFoundError,
    ValidationError,
    first_response_item,
    get_logger,
    log_audit,
    sanitize_log_message,
    validate_confirmation,
    validate_site_id,
)


async def _find_network(client: UniFiClient, site_id: str, **match: Any) -> dict[str, Any] | None:
    """Fetch the site's networks and return the first one whose fields equal ``match``."""
    response = await client.get(f"/ea/sites/{site_id}/rest/networkconf")
    networks: list[dict[str, Any]] = (
        response if isinstance(response, list) else response.get("data", [])
    )
    for network in networks:
        if all(network.get(key) == value for key, value in match.items()):
            return network
    return None


def _dns_enabled_if_set(*servers: str | None) -> dict[str, Any]:
    """UniFi hands out ``dhcpd_dns_N`` only when ``dhcpd_dns_enabled`` is true.

    Without the flag DHCP advertises the gateway as the resolver and the listed servers are
    silently ignored, so setting any server must also set the flag.
    """
    return {"dhcpd_dns_enabled": True} if any(servers) else {}


async def create_network(
    site_id: str,
    name: str,
    vlan_id: int,
    subnet: str,
    settings: Settings,
    purpose: str = "corporate",
    dhcp_enabled: bool = True,
    dhcp_start: str | None = None,
    dhcp_stop: str | None = None,
    dhcp_dns_1: str | None = None,
    dhcp_dns_2: str | None = None,
    dhcp_dns_3: str | None = None,
    dhcp_dns_4: str | None = None,
    domain_name: str | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Create a new network/VLAN.

    Args:
        site_id: Site identifier
        name: Network name
        vlan_id: VLAN ID (1-4094)
        subnet: Network subnet in CIDR notation (e.g., "192.168.1.0/24")
        settings: Application settings
        purpose: Network purpose (corporate, guest, vlan-only)
        dhcp_enabled: Enable DHCP server
        dhcp_start: DHCP range start IP
        dhcp_stop: DHCP range stop IP
        dhcp_dns_1: Primary DNS server
        dhcp_dns_2: Secondary DNS server
        domain_name: Domain name for DHCP
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't create the network

    Returns:
        Created network dictionary or dry-run result

    Raises:
        ConfirmationRequiredError: If confirm is not True
        ValidationError: If validation fails
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "network configuration operation", dry_run)
    logger = get_logger(__name__, settings.log_level)

    # Validate VLAN ID
    if not 1 <= vlan_id <= 4094:
        raise ValidationError(f"Invalid VLAN ID {vlan_id}. Must be between 1 and 4094")

    # Validate purpose
    valid_purposes = ["corporate", "guest", "vlan-only", "wan"]
    if purpose not in valid_purposes:
        raise ValidationError(f"Invalid purpose '{purpose}'. Must be one of: {valid_purposes}")

    # Validate subnet format
    if "/" not in subnet:
        raise ValidationError(f"Invalid subnet '{subnet}'. Must be in CIDR notation")

    # Build network data
    network_data = {
        "name": name,
        "purpose": purpose,
        "vlan_enabled": True,
        "vlan": vlan_id,
        "ip_subnet": subnet,
        "dhcpd_enabled": dhcp_enabled,
    }

    if dhcp_enabled:
        if dhcp_start:
            network_data["dhcpd_start"] = dhcp_start
        if dhcp_stop:
            network_data["dhcpd_stop"] = dhcp_stop
        if dhcp_dns_1:
            network_data["dhcpd_dns_1"] = dhcp_dns_1
        if dhcp_dns_2:
            network_data["dhcpd_dns_2"] = dhcp_dns_2
        if dhcp_dns_3:
            network_data["dhcpd_dns_3"] = dhcp_dns_3
        if dhcp_dns_4:
            network_data["dhcpd_dns_4"] = dhcp_dns_4
        if domain_name:
            network_data["domain_name"] = domain_name
        network_data.update(_dns_enabled_if_set(dhcp_dns_1, dhcp_dns_2, dhcp_dns_3, dhcp_dns_4))

    # Log parameters for audit
    parameters = {
        "site_id": site_id,
        "name": name,
        "vlan_id": vlan_id,
        "subnet": subnet,
        "purpose": purpose,
        "dhcp_enabled": dhcp_enabled,
        "dhcp_start": dhcp_start,
        "dhcp_stop": dhcp_stop,
    }

    if dry_run:
        logger.info(
            sanitize_log_message(f"DRY RUN: Would create network '{name}' in site '{site_id}'")
        )
        log_audit(
            operation="create_network",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_create": network_data}

    try:
        async with UniFiClient(settings) as client:
            await client.authenticate()

            response = await client.post(
                f"/ea/sites/{site_id}/rest/networkconf", json_data=network_data
            )
            created_network: dict[str, Any] | None = first_response_item(response)
            if not created_network:
                # UniFi accepted the write without echoing the record: read it back.
                created_network = await _find_network(client, site_id, name=name, vlan=vlan_id)
            if created_network is None:
                raise ResourceNotFoundError("network", name)

            logger.info(sanitize_log_message(f"Created network '{name}' in site '{site_id}'"))
            log_audit(
                operation="create_network",
                parameters=parameters,
                result="success",
                site_id=site_id,
            )

            return created_network

    except Exception as e:
        logger.error(sanitize_log_message(f"Failed to create network '{name}': {e}"))
        log_audit(
            operation="create_network",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise


async def update_network(
    site_id: str,
    network_id: str,
    settings: Settings,
    name: str | None = None,
    vlan_id: int | None = None,
    subnet: str | None = None,
    dhcp_enabled: bool | None = None,
    dhcp_start: str | None = None,
    dhcp_stop: str | None = None,
    dhcp_dns_1: str | None = None,
    dhcp_dns_2: str | None = None,
    dhcp_dns_3: str | None = None,
    dhcp_dns_4: str | None = None,
    domain_name: str | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Update an existing network.

    Note: Network purpose (corporate, guest, vlan-only) cannot be changed after
    creation. To change purpose, delete and recreate the network.

    Args:
        site_id: Site identifier
        network_id: Network ID
        settings: Application settings
        name: New network name
        vlan_id: New VLAN ID (1-4094)
        subnet: New subnet in CIDR notation
        dhcp_enabled: Enable/disable DHCP
        dhcp_start: New DHCP range start IP
        dhcp_stop: New DHCP range stop IP
        dhcp_dns_1: New primary DNS server
        dhcp_dns_2: New secondary DNS server
        domain_name: New domain name
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't update the network

    Returns:
        Updated network dictionary or dry-run result

    Raises:
        ConfirmationRequiredError: If confirm is not True
        ResourceNotFoundError: If network not found
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "network configuration operation", dry_run)
    logger = get_logger(__name__, settings.log_level)

    # Validate VLAN ID if provided
    if vlan_id is not None and not 1 <= vlan_id <= 4094:
        raise ValidationError(f"Invalid VLAN ID {vlan_id}. Must be between 1 and 4094")

    # Validate subnet format if provided
    if subnet is not None and "/" not in subnet:
        raise ValidationError(f"Invalid subnet '{subnet}'. Must be in CIDR notation")

    changes: dict[str, Any] = {}
    if name is not None:
        changes["name"] = name
    if vlan_id is not None:
        changes["vlan_enabled"] = True
        changes["vlan"] = vlan_id
    if subnet is not None:
        changes["ip_subnet"] = subnet
    if dhcp_enabled is not None:
        changes["dhcpd_enabled"] = dhcp_enabled
    if dhcp_start is not None:
        changes["dhcpd_start"] = dhcp_start
    if dhcp_stop is not None:
        changes["dhcpd_stop"] = dhcp_stop
    for index, server in enumerate((dhcp_dns_1, dhcp_dns_2, dhcp_dns_3, dhcp_dns_4), start=1):
        if server is not None:
            changes[f"dhcpd_dns_{index}"] = server
    if domain_name is not None:
        changes["domain_name"] = domain_name
    changes.update(_dns_enabled_if_set(dhcp_dns_1, dhcp_dns_2, dhcp_dns_3, dhcp_dns_4))

    parameters = {
        "site_id": site_id,
        "network_id": network_id,
        "name": name,
        "vlan_id": vlan_id,
        "subnet": subnet,
        "dhcp_enabled": dhcp_enabled,
        "changes": changes,
    }

    if dry_run:
        logger.info(
            sanitize_log_message(
                f"DRY RUN: Would update network '{network_id}' in site '{site_id}'"
            )
        )
        log_audit(
            operation="update_network",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        # The preview carries the exact field changes the real call sends (it used to echo only
        # name/vlan/subnet/dhcp_enabled, which made a DNS change look as if it would be dropped).
        return {"dry_run": True, "would_update": parameters}

    try:
        async with UniFiClient(settings) as client:
            await client.authenticate()

            existing_network = await _find_network(client, site_id, _id=network_id)
            if not existing_network:
                raise ResourceNotFoundError("network", network_id)

            update_data = existing_network.copy()
            update_data.update(changes)

            response = await client.put(
                f"/ea/sites/{site_id}/rest/networkconf/{network_id}", json_data=update_data
            )
            updated_network: dict[str, Any] | None = first_response_item(response)
            if not updated_network:
                # No record in the reply. The client drops UniFi's ``meta`` block, so an empty
                # ``data`` cannot tell a success from a rejected write: read the stored record
                # back and require every requested field to be there before reporting success.
                updated_network = await _find_network(client, site_id, _id=network_id)
                if updated_network is None:
                    raise ResourceNotFoundError("network", network_id)
                not_applied = sorted(
                    key for key, value in changes.items() if updated_network.get(key) != value
                )
                if not_applied:
                    raise APIError(
                        f"update_network: the controller returned no record and the stored "
                        f"network does not show the requested change for: {', '.join(not_applied)}"
                    )

            logger.info(sanitize_log_message(f"Updated network '{network_id}' in site '{site_id}'"))
            log_audit(
                operation="update_network",
                parameters=parameters,
                result="success",
                site_id=site_id,
            )

            return updated_network

    except Exception as e:
        logger.error(sanitize_log_message(f"Failed to update network '{network_id}': {e}"))
        log_audit(
            operation="update_network",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise


async def delete_network(
    site_id: str,
    network_id: str,
    settings: Settings,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Delete a network.

    Args:
        site_id: Site identifier
        network_id: Network ID
        settings: Application settings
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't delete the network

    Returns:
        Deletion result dictionary

    Raises:
        ConfirmationRequiredError: If confirm is not True
        ResourceNotFoundError: If network not found
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "network configuration operation", dry_run)
    logger = get_logger(__name__, settings.log_level)

    parameters = {"site_id": site_id, "network_id": network_id}

    if dry_run:
        logger.info(
            sanitize_log_message(
                f"DRY RUN: Would delete network '{network_id}' from site '{site_id}'"
            )
        )
        log_audit(
            operation="delete_network",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_delete": network_id}

    try:
        async with UniFiClient(settings) as client:
            await client.authenticate()

            # Verify network exists before deleting
            response = await client.get(f"/ea/sites/{site_id}/rest/networkconf")
            networks_data: list[dict[str, Any]] = (
                response if isinstance(response, list) else response.get("data", [])
            )

            network_exists = any(net.get("_id") == network_id for net in networks_data)
            if not network_exists:
                raise ResourceNotFoundError("network", network_id)

            response = await client.delete(f"/ea/sites/{site_id}/rest/networkconf/{network_id}")

            logger.info(
                sanitize_log_message(f"Deleted network '{network_id}' from site '{site_id}'")
            )
            log_audit(
                operation="delete_network",
                parameters=parameters,
                result="success",
                site_id=site_id,
            )

            return {"success": True, "deleted_network_id": network_id}

    except Exception as e:
        logger.error(sanitize_log_message(f"Failed to delete network '{network_id}': {e}"))
        log_audit(
            operation="delete_network",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise
