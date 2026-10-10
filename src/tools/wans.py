"""WAN connection management tools."""

from ..api.client import UniFiClient
from ..config import Settings
from ..models import WANConnection
from ..utils import get_logger, sanitize_log_message, validate_site_id

logger = get_logger(__name__)


async def list_wan_connections(site_id: str, settings: Settings) -> list[dict]:
    """List all WAN connections for a site.

    Args:
        site_id: Site identifier
        settings: Application settings

    Returns:
        List of WAN connections. Fields the controller does not report are
        omitted rather than returned as ``null``: the Integration v1 list route
        supplies only ``id`` and ``name``, so keeping the nulls would bury those
        two under 20 empty keys.
    """
    site_id = validate_site_id(site_id)
    async with UniFiClient(settings) as client:
        logger.info(sanitize_log_message(f"Listing WAN connections for site {site_id}"))

        if not client.is_authenticated:
            await client.authenticate()

        response = await client.get(f"/integration/v1/sites/{site_id}/wans")
        data = response if isinstance(response, list) else response.get("data", [])

        return [WANConnection(**wan).model_dump(exclude_none=True) for wan in data]
