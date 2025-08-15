"""
Sonarr API client functions.

Functional async client for Sonarr TV series management API.
"""

from typing import Any

import httpx
import structlog

from ..config import Settings

logger = structlog.get_logger(__name__)


async def get_series(
    settings: Settings, client: httpx.AsyncClient | None = None
) -> list[dict[str, Any]]:
    """Get all series from Sonarr."""
    if not settings.sonarr_url or not settings.sonarr_api_key:
        logger.warning("Sonarr URL or API key not configured")
        return []

    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.http_timeout)

    try:
        response = await client.get(
            f"{settings.sonarr_url}/api/v3/series",
            headers={"X-Api-Key": settings.sonarr_api_key},
        )
        response.raise_for_status()
        return response.json()

    except httpx.HTTPError as e:
        logger.error("Failed to get series from Sonarr", error=str(e))
        return []
    finally:
        if should_close_client:
            await client.aclose()


async def get_series_by_id(
    series_id: int, settings: Settings, client: httpx.AsyncClient | None = None
) -> dict[str, Any] | None:
    """Get series by ID from Sonarr."""
    if not settings.sonarr_url or not settings.sonarr_api_key:
        logger.warning("Sonarr URL or API key not configured")
        return None

    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.http_timeout)

    try:
        response = await client.get(
            f"{settings.sonarr_url}/api/v3/series/{series_id}",
            headers={"X-Api-Key": settings.sonarr_api_key},
        )
        response.raise_for_status()
        return response.json()

    except httpx.HTTPError as e:
        logger.error(
            "Failed to get series by ID from Sonarr", error=str(e), series_id=series_id
        )
        return None
    finally:
        if should_close_client:
            await client.aclose()


async def search_series(
    term: str, settings: Settings, client: httpx.AsyncClient | None = None
) -> list[dict[str, Any]]:
    """Search for series in Sonarr lookup."""
    if not settings.sonarr_url or not settings.sonarr_api_key:
        logger.warning("Sonarr URL or API key not configured")
        return []

    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.http_timeout)

    try:
        response = await client.get(
            f"{settings.sonarr_url}/api/v3/series/lookup",
            headers={"X-Api-Key": settings.sonarr_api_key},
            params={"term": term},
        )
        response.raise_for_status()
        return response.json()

    except httpx.HTTPError as e:
        logger.error("Failed to search series in Sonarr", error=str(e), term=term)
        return []
    finally:
        if should_close_client:
            await client.aclose()


async def add_series(
    series_data: dict[str, Any],
    settings: Settings,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any] | None:
    """Add series to Sonarr."""
    if not settings.sonarr_url or not settings.sonarr_api_key:
        logger.warning("Sonarr URL or API key not configured")
        return None

    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.http_timeout)

    try:
        response = await client.post(
            f"{settings.sonarr_url}/api/v3/series",
            headers={
                "X-Api-Key": settings.sonarr_api_key,
                "Content-Type": "application/json",
            },
            json=series_data,
        )
        response.raise_for_status()
        return response.json()

    except httpx.HTTPError as e:
        logger.error(
            "Failed to add series to Sonarr",
            error=str(e),
            series_title=series_data.get("title"),
        )
        return None
    finally:
        if should_close_client:
            await client.aclose()


async def get_quality_profiles(
    settings: Settings, client: httpx.AsyncClient | None = None
) -> list[dict[str, Any]]:
    """Get quality profiles from Sonarr."""
    if not settings.sonarr_url or not settings.sonarr_api_key:
        logger.warning("Sonarr URL or API key not configured")
        return []

    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.http_timeout)

    try:
        response = await client.get(
            f"{settings.sonarr_url}/api/v3/qualityprofile",
            headers={"X-Api-Key": settings.sonarr_api_key},
        )
        response.raise_for_status()
        return response.json()

    except httpx.HTTPError as e:
        logger.error("Failed to get quality profiles from Sonarr", error=str(e))
        return []
    finally:
        if should_close_client:
            await client.aclose()


async def get_root_folders(
    settings: Settings, client: httpx.AsyncClient | None = None
) -> list[dict[str, Any]]:
    """Get root folders from Sonarr."""
    if not settings.sonarr_url or not settings.sonarr_api_key:
        logger.warning("Sonarr URL or API key not configured")
        return []

    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.http_timeout)

    try:
        response = await client.get(
            f"{settings.sonarr_url}/api/v3/rootfolder",
            headers={"X-Api-Key": settings.sonarr_api_key},
        )
        response.raise_for_status()
        return response.json()

    except httpx.HTTPError as e:
        logger.error("Failed to get root folders from Sonarr", error=str(e))
        return []
    finally:
        if should_close_client:
            await client.aclose()


async def trigger_series_search(
    series_id: int, settings: Settings, client: httpx.AsyncClient | None = None
) -> bool:
    """Trigger search for all episodes of a series in Sonarr."""
    if not settings.sonarr_url or not settings.sonarr_api_key:
        logger.warning("Sonarr URL or API key not configured")
        return False

    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.http_timeout)

    try:
        command_data = {"name": "SeriesSearch", "seriesId": series_id}

        response = await client.post(
            f"{settings.sonarr_url}/api/v3/command",
            headers={
                "X-Api-Key": settings.sonarr_api_key,
                "Content-Type": "application/json",
            },
            json=command_data,
        )
        response.raise_for_status()
        return True

    except httpx.HTTPError as e:
        logger.error(
            "Failed to trigger series search in Sonarr",
            error=str(e),
            series_id=series_id,
        )
        return False
    finally:
        if should_close_client:
            await client.aclose()
