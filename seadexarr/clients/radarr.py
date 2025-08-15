"""
Radarr API client functions.

Functional async client for Radarr movie management API.
"""

from typing import Any

import httpx
import structlog

from ..config import Settings

logger = structlog.get_logger(__name__)


async def get_movies(
    settings: Settings, client: httpx.AsyncClient | None = None
) -> list[dict[str, Any]]:
    """Get all movies from Radarr."""
    if not settings.radarr_url or not settings.radarr_api_key:
        logger.warning("Radarr URL or API key not configured")
        return []

    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.http_timeout)

    try:
        response = await client.get(
            f"{settings.radarr_url}/api/v3/movie",
            headers={"X-Api-Key": settings.radarr_api_key},
        )
        response.raise_for_status()
        return response.json()

    except httpx.HTTPError as e:
        logger.error("Failed to get movies from Radarr", error=str(e))
        return []
    finally:
        if should_close_client:
            await client.aclose()


async def get_movie_by_id(
    movie_id: int, settings: Settings, client: httpx.AsyncClient | None = None
) -> dict[str, Any] | None:
    """Get movie by ID from Radarr."""
    if not settings.radarr_url or not settings.radarr_api_key:
        logger.warning("Radarr URL or API key not configured")
        return None

    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.http_timeout)

    try:
        response = await client.get(
            f"{settings.radarr_url}/api/v3/movie/{movie_id}",
            headers={"X-Api-Key": settings.radarr_api_key},
        )
        response.raise_for_status()
        return response.json()

    except httpx.HTTPError as e:
        logger.error(
            "Failed to get movie by ID from Radarr", error=str(e), movie_id=movie_id
        )
        return None
    finally:
        if should_close_client:
            await client.aclose()


async def search_movies(
    term: str, settings: Settings, client: httpx.AsyncClient | None = None
) -> list[dict[str, Any]]:
    """Search for movies in Radarr lookup."""
    if not settings.radarr_url or not settings.radarr_api_key:
        logger.warning("Radarr URL or API key not configured")
        return []

    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.http_timeout)

    try:
        response = await client.get(
            f"{settings.radarr_url}/api/v3/movie/lookup",
            headers={"X-Api-Key": settings.radarr_api_key},
            params={"term": term},
        )
        response.raise_for_status()
        return response.json()

    except httpx.HTTPError as e:
        logger.error("Failed to search movies in Radarr", error=str(e), term=term)
        return []
    finally:
        if should_close_client:
            await client.aclose()


async def add_movie(
    movie_data: dict[str, Any],
    settings: Settings,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any] | None:
    """Add movie to Radarr."""
    if not settings.radarr_url or not settings.radarr_api_key:
        logger.warning("Radarr URL or API key not configured")
        return None

    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.http_timeout)

    try:
        response = await client.post(
            f"{settings.radarr_url}/api/v3/movie",
            headers={
                "X-Api-Key": settings.radarr_api_key,
                "Content-Type": "application/json",
            },
            json=movie_data,
        )
        response.raise_for_status()
        return response.json()

    except httpx.HTTPError as e:
        logger.error(
            "Failed to add movie to Radarr",
            error=str(e),
            movie_title=movie_data.get("title"),
        )
        return None
    finally:
        if should_close_client:
            await client.aclose()


async def get_quality_profiles(
    settings: Settings, client: httpx.AsyncClient | None = None
) -> list[dict[str, Any]]:
    """Get quality profiles from Radarr."""
    if not settings.radarr_url or not settings.radarr_api_key:
        logger.warning("Radarr URL or API key not configured")
        return []

    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.http_timeout)

    try:
        response = await client.get(
            f"{settings.radarr_url}/api/v3/qualityprofile",
            headers={"X-Api-Key": settings.radarr_api_key},
        )
        response.raise_for_status()
        return response.json()

    except httpx.HTTPError as e:
        logger.error("Failed to get quality profiles from Radarr", error=str(e))
        return []
    finally:
        if should_close_client:
            await client.aclose()


async def get_root_folders(
    settings: Settings, client: httpx.AsyncClient | None = None
) -> list[dict[str, Any]]:
    """Get root folders from Radarr."""
    if not settings.radarr_url or not settings.radarr_api_key:
        logger.warning("Radarr URL or API key not configured")
        return []

    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.http_timeout)

    try:
        response = await client.get(
            f"{settings.radarr_url}/api/v3/rootfolder",
            headers={"X-Api-Key": settings.radarr_api_key},
        )
        response.raise_for_status()
        return response.json()

    except httpx.HTTPError as e:
        logger.error("Failed to get root folders from Radarr", error=str(e))
        return []
    finally:
        if should_close_client:
            await client.aclose()


async def trigger_movie_search(
    movie_id: int, settings: Settings, client: httpx.AsyncClient | None = None
) -> bool:
    """Trigger search for a movie in Radarr."""
    if not settings.radarr_url or not settings.radarr_api_key:
        logger.warning("Radarr URL or API key not configured")
        return False

    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.http_timeout)

    try:
        command_data = {"name": "MoviesSearch", "movieIds": [movie_id]}

        response = await client.post(
            f"{settings.radarr_url}/api/v3/command",
            headers={
                "X-Api-Key": settings.radarr_api_key,
                "Content-Type": "application/json",
            },
            json=command_data,
        )
        response.raise_for_status()
        return True

    except httpx.HTTPError as e:
        logger.error(
            "Failed to trigger movie search in Radarr", error=str(e), movie_id=movie_id
        )
        return False
    finally:
        if should_close_client:
            await client.aclose()
