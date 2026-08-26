"""Application information tools."""

from ..api.client import UniFiClient
from ..config import Settings
from ..utils import get_logger

logger = get_logger(__name__)


async def get_application_info(settings: Settings) -> dict:
    """Get UniFi Network application information.

    Args:
        settings: Application settings

    Returns:
        Application information dictionary

    Example:
        >>> info = await get_application_info(settings)
        >>> print(info["version"])
    """
    async with UniFiClient(settings) as client:
        logger.info("Fetching application information")

        # Authenticate if not already done
        if not client.is_authenticated:
            await client.authenticate()

        # The real endpoint is /integration/v1/info, NOT /integration/v1/application/info
        # — the latter 404s ("No endpoint GET /integration/v1/application/info") on every
        # firmware tested. Response shape is also much narrower than earlier assumed:
        # verified live against Network 10.5.67, it returns only {"applicationVersion": "..."}.
        # No build/deploymentType/capabilities/systemInfo fields exist at this endpoint.
        response = await client.get(settings.get_integration_path("info"))

        data = response if isinstance(response, dict) else {}
        if "data" in data and isinstance(data["data"], (dict, list)):
            nested = data["data"]
            data = nested[0] if isinstance(nested, list) and nested else nested

        return {
            "version": data.get("applicationVersion"),
        }
