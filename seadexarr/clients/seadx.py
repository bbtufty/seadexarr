"""
SeaDx API client functions.

Functional async client for SeaDx releases API.
"""

from typing import Any

import httpx
import structlog

from ..config import Settings

logger = structlog.get_logger(__name__)


async def get_release_by_id(
    release_id: str, settings: Settings, client: httpx.AsyncClient | None = None
) -> dict[str, Any] | None:
    """Get release information by SeaDx ID."""
    if not settings.seadx_api_key:
        logger.warning("No SeaDx API key configured")
        return None

    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.http_timeout)

    try:
        response = await client.get(
            f"{settings.seadx_base_url}/api/releases/{release_id}",
            headers={"Authorization": f"Bearer {settings.seadx_api_key}"},
        )
        response.raise_for_status()
        return response.json()

    except httpx.HTTPError as e:
        logger.error(
            "Failed to fetch release from SeaDx", error=str(e), release_id=release_id
        )
        return None
    finally:
        if should_close_client:
            await client.aclose()


async def search_releases(
    query: str,
    settings: Settings,
    media_type: str = "anime",
    limit: int = 10,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Search for releases by title."""
    if not settings.seadx_api_key:
        logger.warning("No SeaDx API key configured")
        return []

    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.http_timeout)

    try:
        params = {"q": query, "type": media_type, "limit": limit}

        response = await client.get(
            f"{settings.seadx_base_url}/api/releases/search",
            headers={"Authorization": f"Bearer {settings.seadx_api_key}"},
            params=params,
        )
        response.raise_for_status()

        data = response.json()
        return data.get("releases", [])

    except httpx.HTTPError as e:
        logger.error("Failed to search releases on SeaDx", error=str(e), query=query)
        return []
    finally:
        if should_close_client:
            await client.aclose()


async def get_releases_by_anilist_id(
    anilist_id: int, settings: Settings, client: httpx.AsyncClient | None = None
) -> list[dict[str, Any]]:
    """Get releases by AniList ID."""
    if not settings.seadx_api_key:
        logger.warning("No SeaDx API key configured")
        return []

    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.http_timeout)

    try:
        response = await client.get(
            f"{settings.seadx_base_url}/api/releases/by-anilist/{anilist_id}",
            headers={"Authorization": f"Bearer {settings.seadx_api_key}"},
        )
        response.raise_for_status()

        data = response.json()
        return data.get("releases", [])

    except httpx.HTTPError as e:
        logger.error(
            "Failed to get releases by AniList ID", error=str(e), anilist_id=anilist_id
        )
        return []
    finally:
        if should_close_client:
            await client.aclose()


async def get_torrent_file(
    release_id: str, settings: Settings, client: httpx.AsyncClient | None = None
) -> bytes | None:
    """Download torrent file for a release."""
    if not settings.seadx_api_key:
        logger.warning("No SeaDx API key configured")
        return None

    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.http_timeout)

    try:
        response = await client.get(
            f"{settings.seadx_base_url}/api/releases/{release_id}/torrent",
            headers={"Authorization": f"Bearer {settings.seadx_api_key}"},
        )
        response.raise_for_status()

        if response.headers.get("content-type") == "application/x-bittorrent":
            return response.content
        else:
            logger.error(
                "Invalid torrent file response",
                content_type=response.headers.get("content-type"),
            )
            return None

    except httpx.HTTPError as e:
        logger.error(
            "Failed to download torrent file", error=str(e), release_id=release_id
        )
        return None
    finally:
        if should_close_client:
            await client.aclose()


async def get_release_stats(
    settings: Settings, client: httpx.AsyncClient | None = None
) -> dict[str, Any] | None:
    """Get SeaDx release statistics."""
    if not settings.seadx_api_key:
        logger.warning("No SeaDx API key configured")
        return None

    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.http_timeout)

    try:
        response = await client.get(
            f"{settings.seadx_base_url}/api/stats",
            headers={"Authorization": f"Bearer {settings.seadx_api_key}"},
        )
        response.raise_for_status()
        return response.json()

    except httpx.HTTPError as e:
        logger.error("Failed to get SeaDx stats", error=str(e))
        return None
    finally:
        if should_close_client:
            await client.aclose()
