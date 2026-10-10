"""Traffic Matching List management MCP tools."""

from typing import Any

from ..api import UniFiClient
from ..config import Settings
from ..models.traffic_matching_list import (
    TrafficMatchingListCreate,
    TrafficMatchingListUpdate,
    parse_traffic_matching_list,
)
from ..utils import (
    ResourceNotFoundError,
    ValidationError,
    get_logger,
    log_audit,
    sanitize_log_message,
    validate_confirmation,
    validate_limit_offset,
    validate_site_id,
)

_VALID_LIST_TYPES = ("PORTS", "IPV4_ADDRESSES", "IPV6_ADDRESSES")


def _ensure_cloud_api(settings: Settings) -> None:
    """No-op retained for call-site compatibility.

    Traffic matching lists were long believed cloud-only; that stopped being true once the
    Integration API shipped locally (GA on Network App >= 9.3). Verified live against
    Network 10.5.67: GET .../traffic-matching-lists returns 200.
    """
    return


def _normalise_traffic_matching_item(list_type: str, item: Any) -> dict[str, Any]:
    """Convert a simple item (int port, str IP/CIDR, or a range dict) into the API's
    discriminated item shape for the given list `type`.

    Accepts:

    * PORTS: an `int` port number, or `{"start": int, "stop": int}` for a range.
    * IPV4_ADDRESSES / IPV6_ADDRESSES: a `str` address (CIDR notation, containing '/', is
      treated as a subnet; anything else as a single address), or — IPv4 only —
      `{"start": str, "stop": str}` for an address range. IPv6 has no documented range
      variant.

    Already API-shaped dicts (`{"type": ..., "value"/"start"/"stop": ...}`) pass through
    unchanged, for callers who want to be fully explicit.
    """
    if isinstance(item, dict) and "type" in item:
        return item

    if list_type == "PORTS":
        if isinstance(item, dict):
            if "start" not in item or "stop" not in item:
                raise ValidationError(
                    f"PORTS range item must have 'start' and 'stop': got {item!r}"
                )
            return {"type": "PORT_NUMBER_RANGE", "start": item["start"], "stop": item["stop"]}
        return {"type": "PORT_NUMBER", "value": item}

    # IPV4_ADDRESSES / IPV6_ADDRESSES
    if isinstance(item, dict):
        if list_type != "IPV4_ADDRESSES":
            raise ValidationError(
                f"Address ranges are only documented for IPV4_ADDRESSES, not {list_type}."
            )
        if "start" not in item or "stop" not in item:
            raise ValidationError(
                f"{list_type} range item must have 'start' and 'stop': got {item!r}"
            )
        return {"type": "IP_ADDRESS_RANGE", "start": item["start"], "stop": item["stop"]}
    if "/" in item:
        return {"type": "SUBNET", "value": item}
    return {"type": "IP_ADDRESS", "value": item}


async def list_traffic_matching_lists(
    site_id: str,
    settings: Settings,
    limit: int | None = None,
    offset: int | None = None,
) -> list[dict[str, Any]]:
    """List all traffic matching lists in a site (read-only).

    Args:
        site_id: Site identifier
        settings: Application settings
        limit: Maximum number of lists to return
        offset: Number of lists to skip

    Returns:
        List of traffic matching list dictionaries
    """
    site_id = validate_site_id(site_id)
    limit, offset = validate_limit_offset(limit, offset)
    logger = get_logger(__name__, settings.log_level)
    _ensure_cloud_api(settings)

    async with UniFiClient(settings) as client:
        await client.authenticate()

        resolved_site_id = await client.resolve_site_id(site_id)
        endpoint = settings.get_integration_path(f"sites/{resolved_site_id}/traffic-matching-lists")
        response = await client.get(endpoint)
        lists_data: list[dict[str, Any]] = (
            response if isinstance(response, list) else response.get("data", [])
        )

        # Apply pagination
        paginated = lists_data[offset : offset + limit]

        logger.info(
            sanitize_log_message(
                f"Retrieved {len(paginated)} traffic matching lists for site '{site_id}'"
            )
        )
        return [parse_traffic_matching_list(lst).model_dump() for lst in paginated]


async def get_traffic_matching_list(
    site_id: str,
    list_id: str,
    settings: Settings,
) -> dict[str, Any]:
    """Get details for a specific traffic matching list.

    Args:
        site_id: Site identifier
        list_id: Traffic matching list ID
        settings: Application settings

    Returns:
        Traffic matching list dictionary

    Raises:
        ResourceNotFoundError: If list not found
    """
    site_id = validate_site_id(site_id)
    logger = get_logger(__name__, settings.log_level)
    _ensure_cloud_api(settings)

    async with UniFiClient(settings) as client:
        await client.authenticate()

        resolved_site_id = await client.resolve_site_id(site_id)
        endpoint = settings.get_integration_path(
            f"sites/{resolved_site_id}/traffic-matching-lists/{list_id}"
        )
        response = await client.get(endpoint)

        if isinstance(response, dict) and "data" in response:
            list_data = response["data"]
        else:
            list_data = response

        if not list_data:
            raise ResourceNotFoundError("traffic_matching_list", list_id)

        logger.info(sanitize_log_message(f"Retrieved traffic matching list {list_id}"))
        return parse_traffic_matching_list(list_data).model_dump()


async def create_traffic_matching_list(
    site_id: str,
    list_type: str,
    name: str,
    items: list[int | str | dict[str, Any]],
    settings: Settings,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Create a new traffic matching list.

    Args:
        site_id: Site identifier
        list_type: List type (PORTS, IPV4_ADDRESSES, IPV6_ADDRESSES)
        name: List name
        items: List items. For PORTS: an int port number, or a
            `{"start": int, "stop": int}` range. For IPV4_ADDRESSES/IPV6_ADDRESSES: a str
            address or CIDR subnet, or — IPv4 only — a `{"start": str, "stop": str}`
            address range.
        settings: Application settings
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't create

    Returns:
        Created list dictionary or dry-run result

    Raises:
        ConfirmationRequiredError: If confirm is not True
        ValidationError: If validation fails
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "traffic matching list operation", dry_run)
    logger = get_logger(__name__, settings.log_level)
    _ensure_cloud_api(settings)

    if list_type not in _VALID_LIST_TYPES:
        raise ValidationError(
            f"Invalid list type '{list_type}'. Must be one of: {_VALID_LIST_TYPES}"
        )

    if not items:
        raise ValidationError("Items list cannot be empty")

    normalised_items = [_normalise_traffic_matching_item(list_type, item) for item in items]

    # Raises pydantic.ValidationError with the real per-item schema if a caller passes,
    # e.g., a string port or an out-of-range value.
    create_data = TrafficMatchingListCreate(type=list_type, name=name, items=normalised_items)

    parameters = {
        "site_id": site_id,
        "type": list_type,
        "name": name,
        "items_count": len(items),
    }

    if dry_run:
        logger.info(
            sanitize_log_message(
                f"DRY RUN: Would create traffic matching list '{name}' in site '{site_id}'"
            )
        )
        log_audit(
            operation="create_traffic_matching_list",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_create": create_data.model_dump()}

    try:
        async with UniFiClient(settings) as client:
            await client.authenticate()

            resolved_site_id = await client.resolve_site_id(site_id)
            endpoint = settings.get_integration_path(
                f"sites/{resolved_site_id}/traffic-matching-lists"
            )
            response = await client.post(
                endpoint,
                json_data=create_data.model_dump(),
            )
            created_list: dict[str, Any] = (
                response if isinstance(response, list) else response.get("data", response)
            )

            logger.info(
                sanitize_log_message(f"Created traffic matching list '{name}' in site '{site_id}'")
            )
            log_audit(
                operation="create_traffic_matching_list",
                parameters=parameters,
                result="success",
                site_id=site_id,
            )

            return parse_traffic_matching_list(created_list).model_dump()

    except Exception as e:
        logger.error(sanitize_log_message(f"Failed to create traffic matching list '{name}': {e}"))
        log_audit(
            operation="create_traffic_matching_list",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise


async def update_traffic_matching_list(
    site_id: str,
    list_id: str,
    settings: Settings,
    list_type: str | None = None,
    name: str | None = None,
    items: list[int | str | dict[str, Any]] | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Update an existing traffic matching list.

    Args:
        site_id: Site identifier
        list_id: Traffic matching list ID
        settings: Application settings
        list_type: New list type
        name: New list name
        items: New list items — see `create_traffic_matching_list` for the accepted shapes.
            Validated against the list's EFFECTIVE type (`list_type` if given here,
            otherwise the list's existing type, fetched first).
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't update

    Returns:
        Updated list dictionary or dry-run result

    Raises:
        ConfirmationRequiredError: If confirm is not True
        ResourceNotFoundError: If list not found
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "traffic matching list operation", dry_run)
    logger = get_logger(__name__, settings.log_level)
    _ensure_cloud_api(settings)

    if list_type is not None and list_type not in _VALID_LIST_TYPES:
        raise ValidationError(
            f"Invalid list type '{list_type}'. Must be one of: {_VALID_LIST_TYPES}"
        )

    if items is not None and len(items) == 0:
        raise ValidationError("Items list cannot be empty")

    parameters = {
        "site_id": site_id,
        "list_id": list_id,
        "type": list_type,
        "name": name,
        "items_count": len(items) if items else None,
    }

    if dry_run:
        logger.info(
            sanitize_log_message(
                f"DRY RUN: Would update traffic matching list '{list_id}' in site '{site_id}'"
            )
        )
        log_audit(
            operation="update_traffic_matching_list",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_update": parameters}

    try:
        async with UniFiClient(settings) as client:
            await client.authenticate()

            resolved_site_id = await client.resolve_site_id(site_id)

            # Get existing list — needed both to 404 correctly and to know the effective
            # type against which `items` (if given without `list_type`) must validate.
            endpoint = settings.get_integration_path(
                f"sites/{resolved_site_id}/traffic-matching-lists/{list_id}"
            )
            response = await client.get(endpoint)
            existing_list = (
                response if isinstance(response, list) else response.get("data", response)
            )

            if not existing_list:
                raise ResourceNotFoundError("traffic_matching_list", list_id)

            effective_type = list_type or existing_list.get("type")

            # Build update data
            update_data = existing_list.copy()

            if list_type is not None:
                update_data["type"] = list_type
            if name is not None:
                update_data["name"] = name
            if items is not None:
                normalised_items = [
                    _normalise_traffic_matching_item(effective_type, item) for item in items
                ]
                update_data["items"] = normalised_items

            # Raises pydantic.ValidationError against the real per-item schema.
            validated = TrafficMatchingListUpdate(
                type=update_data.get("type"),
                name=update_data.get("name"),
                items=update_data.get("items"),
            )
            if validated.items is not None:
                update_data["items"] = validated.items

            endpoint = settings.get_integration_path(
                f"sites/{resolved_site_id}/traffic-matching-lists/{list_id}"
            )
            # The PUT schema is {type, name, items}. The fetched record also carries "id" (and may
            # carry other read-only keys); the controller rejects them with
            # 400 "Unknown request body property '$.id'", so send only the writable fields.
            put_body = {k: update_data[k] for k in ("type", "name", "items") if k in update_data}
            response = await client.put(
                endpoint,
                json_data=put_body,
            )
            updated_list: dict[str, Any] = (
                response if isinstance(response, list) else response.get("data", response)
            )

            logger.info(
                sanitize_log_message(
                    f"Updated traffic matching list '{list_id}' in site '{site_id}'"
                )
            )
            log_audit(
                operation="update_traffic_matching_list",
                parameters=parameters,
                result="success",
                site_id=site_id,
            )

            return parse_traffic_matching_list(updated_list).model_dump()

    except Exception as e:
        logger.error(
            sanitize_log_message(f"Failed to update traffic matching list '{list_id}': {e}")
        )
        log_audit(
            operation="update_traffic_matching_list",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise


async def delete_traffic_matching_list(
    site_id: str,
    list_id: str,
    settings: Settings,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Delete a traffic matching list.

    Args:
        site_id: Site identifier
        list_id: Traffic matching list ID
        settings: Application settings
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't delete

    Returns:
        Deletion result dictionary

    Raises:
        ConfirmationRequiredError: If confirm is not True
        ResourceNotFoundError: If list not found
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "traffic matching list operation", dry_run)
    logger = get_logger(__name__, settings.log_level)
    _ensure_cloud_api(settings)

    parameters = {"site_id": site_id, "list_id": list_id}

    if dry_run:
        logger.info(
            f"DRY RUN: Would delete traffic matching list '{list_id}' from site '{site_id}'"
        )
        log_audit(
            operation="delete_traffic_matching_list",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_delete": list_id}

    try:
        async with UniFiClient(settings) as client:
            await client.authenticate()

            resolved_site_id = await client.resolve_site_id(site_id)

            # Verify list exists before deleting
            endpoint = settings.get_integration_path(
                f"sites/{resolved_site_id}/traffic-matching-lists/{list_id}"
            )
            try:
                await client.get(endpoint)
            except Exception as err:
                raise ResourceNotFoundError("traffic_matching_list", list_id) from err

            await client.delete(endpoint)

            logger.info(
                sanitize_log_message(
                    f"Deleted traffic matching list '{list_id}' from site '{site_id}'"
                )
            )
            log_audit(
                operation="delete_traffic_matching_list",
                parameters=parameters,
                result="success",
                site_id=site_id,
            )

            return {"success": True, "deleted_list_id": list_id}

    except Exception as e:
        logger.error(
            sanitize_log_message(f"Failed to delete traffic matching list '{list_id}': {e}")
        )
        log_audit(
            operation="delete_traffic_matching_list",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise
