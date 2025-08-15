"""
AniList API client functions.

Functional async client for AniList GraphQL API interactions.
"""

from typing import Any

import httpx
import structlog

from ..config import Settings

logger = structlog.get_logger(__name__)


async def get_media_by_id(
    media_id: int, settings: Settings, client: httpx.AsyncClient | None = None
) -> dict[str, Any] | None:
    """Get anime/manga information by AniList ID."""
    if not settings.anilist_access_token:
        logger.warning("No AniList access token configured")
        return None

    query = """
    query ($id: Int) {
        Media(id: $id) {
            id
            title {
                romaji
                english
                native
            }
            format
            episodes
            status
            startDate {
                year
                month
                day
            }
            endDate {
                year
                month
                day
            }
            genres
            tags {
                name
                rank
            }
        }
    }
    """

    variables = {"id": media_id}

    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.http_timeout)

    try:
        response = await client.post(
            "https://graphql.anilist.co",
            json={"query": query, "variables": variables},
            headers={
                "Authorization": f"Bearer {settings.anilist_access_token}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()

        data = response.json()
        if "errors" in data:
            logger.error("AniList API error", errors=data["errors"])
            return None

        return data.get("data", {}).get("Media")

    except httpx.HTTPError as e:
        logger.error(
            "Failed to fetch media from AniList", error=str(e), media_id=media_id
        )
        return None
    finally:
        if should_close_client:
            await client.aclose()


async def search_media(
    query: str,
    settings: Settings,
    media_type: str = "ANIME",
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Search for anime/manga by title."""
    if not settings.anilist_access_token:
        logger.warning("No AniList access token configured")
        return []

    graphql_query = """
    query ($search: String, $type: MediaType) {
        Page(page: 1, perPage: 10) {
            media(search: $search, type: $type) {
                id
                title {
                    romaji
                    english
                    native
                }
                format
                episodes
                status
                startDate {
                    year
                }
                genres
            }
        }
    }
    """

    variables = {"search": query, "type": media_type}

    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.http_timeout)

    try:
        response = await client.post(
            "https://graphql.anilist.co",
            json={"query": graphql_query, "variables": variables},
            headers={
                "Authorization": f"Bearer {settings.anilist_access_token}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()

        data = response.json()
        if "errors" in data:
            logger.error("AniList API error", errors=data["errors"])
            return []

        page_data = data.get("data", {}).get("Page", {})
        return page_data.get("media", [])

    except httpx.HTTPError as e:
        logger.error("Failed to search media on AniList", error=str(e), query=query)
        return []
    finally:
        if should_close_client:
            await client.aclose()


async def get_user_anime_list(
    username: str, settings: Settings, client: httpx.AsyncClient | None = None
) -> list[dict[str, Any]]:
    """Get user's anime list from AniList."""
    if not settings.anilist_access_token:
        logger.warning("No AniList access token configured")
        return []

    query = """
    query ($username: String) {
        User(name: $username) {
            mediaListOptions {
                scoreFormat
            }
        }
        MediaListCollection(userName: $username, type: ANIME) {
            lists {
                name
                entries {
                    id
                    score
                    status
                    progress
                    media {
                        id
                        title {
                            romaji
                            english
                        }
                        episodes
                        format
                    }
                }
            }
        }
    }
    """

    variables = {"username": username}

    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.http_timeout)

    try:
        response = await client.post(
            "https://graphql.anilist.co",
            json={"query": query, "variables": variables},
            headers={
                "Authorization": f"Bearer {settings.anilist_access_token}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()

        data = response.json()
        if "errors" in data:
            logger.error("AniList API error", errors=data["errors"])
            return []

        collection = data.get("data", {}).get("MediaListCollection", {})

        # Flatten all entries from all lists
        all_entries = []
        for list_data in collection.get("lists", []):
            all_entries.extend(list_data.get("entries", []))

        return all_entries

    except httpx.HTTPError as e:
        logger.error("Failed to get user anime list", error=str(e), username=username)
        return []
    finally:
        if should_close_client:
            await client.aclose()
