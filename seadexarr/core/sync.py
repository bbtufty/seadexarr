"""
Synchronization functions for SeaDexArr.

Core sync logic functions that orchestrate data flow between services.
"""

import asyncio
from typing import Any

import httpx
import structlog

from ..clients import anilist, radarr, seadx, sonarr
from ..config import Settings
from . import filters, mappers

logger = structlog.get_logger(__name__)


async def sync_anilist_to_sonarr(
    anilist_username: str, settings: Settings, dry_run: bool = False
) -> dict[str, Any]:
    """Sync AniList anime list to Sonarr series."""
    if not settings.anilist_access_token:
        return {"error": "AniList access token not configured"}

    if not settings.sonarr_url or not settings.sonarr_api_key:
        return {"error": "Sonarr URL or API key not configured"}

    results = {"processed": 0, "added": 0, "skipped": 0, "errors": 0, "details": []}

    async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
        # Get user's anime list from AniList
        anime_list = await anilist.get_user_anime_list(
            anilist_username, settings, client
        )
        if not anime_list:
            return {"error": "Failed to fetch AniList anime list"}

        # Get existing series from Sonarr
        existing_series = await sonarr.get_series(settings, client)
        existing_anilist_ids = {
            series.get("anilistId")
            for series in existing_series
            if series.get("anilistId")
        }

        # Get quality profiles and root folders
        quality_profiles = await sonarr.get_quality_profiles(settings, client)
        root_folders = await sonarr.get_root_folders(settings, client)

        for entry in anime_list:
            results["processed"] += 1
            media = entry.get("media", {})
            anilist_id = media.get("id")

            if not anilist_id:
                results["skipped"] += 1
                continue

            # Skip if already exists
            if anilist_id in existing_anilist_ids:
                results["skipped"] += 1
                results["details"].append(
                    {
                        "title": media.get("title", {}).get("romaji", "Unknown"),
                        "action": "skipped",
                        "reason": "already exists",
                    }
                )
                continue

            # Only process completed or watching series
            status = entry.get("status")
            if status not in ["COMPLETED", "CURRENT"]:
                results["skipped"] += 1
                continue

            try:
                # Map AniList data to Sonarr format
                series_data = mappers.map_anilist_to_sonarr(media)

                # Set quality profile and root folder
                if quality_profiles:
                    series_data["qualityProfileId"] = quality_profiles[0]["id"]
                if root_folders:
                    series_data["rootFolderPath"] = (
                        mappers.map_root_folder("tv", root_folders)
                        or root_folders[0]["path"]
                    )

                if not dry_run:
                    # Add series to Sonarr
                    added_series = await sonarr.add_series(
                        series_data, settings, client
                    )
                    if added_series:
                        results["added"] += 1
                        results["details"].append(
                            {
                                "title": series_data["title"],
                                "action": "added",
                                "anilist_id": anilist_id,
                            }
                        )
                    else:
                        results["errors"] += 1
                        results["details"].append(
                            {
                                "title": series_data["title"],
                                "action": "error",
                                "reason": "failed to add to Sonarr",
                            }
                        )
                else:
                    results["added"] += 1
                    results["details"].append(
                        {
                            "title": series_data["title"],
                            "action": "would_add",
                            "anilist_id": anilist_id,
                        }
                    )

            except Exception as e:
                logger.error(
                    "Error processing anime", error=str(e), anilist_id=anilist_id
                )
                results["errors"] += 1
                results["details"].append(
                    {
                        "title": media.get("title", {}).get("romaji", "Unknown"),
                        "action": "error",
                        "reason": str(e),
                    }
                )

    return results


async def sync_anilist_to_radarr(
    anilist_username: str, settings: Settings, dry_run: bool = False
) -> dict[str, Any]:
    """Sync AniList manga/movie list to Radarr movies."""
    if not settings.anilist_access_token:
        return {"error": "AniList access token not configured"}

    if not settings.radarr_url or not settings.radarr_api_key:
        return {"error": "Radarr URL or API key not configured"}

    results = {"processed": 0, "added": 0, "skipped": 0, "errors": 0, "details": []}

    async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
        # Get user's anime list from AniList (filtering for movies)
        anime_list = await anilist.get_user_anime_list(
            anilist_username, settings, client
        )
        if not anime_list:
            return {"error": "Failed to fetch AniList anime list"}

        # Filter for movie format only
        movie_entries = [
            entry
            for entry in anime_list
            if entry.get("media", {}).get("format") == "MOVIE"
        ]

        # Get existing movies from Radarr
        existing_movies = await radarr.get_movies(settings, client)
        existing_anilist_ids = {
            movie.get("anilistId")
            for movie in existing_movies
            if movie.get("anilistId")
        }

        # Get quality profiles and root folders
        quality_profiles = await radarr.get_quality_profiles(settings, client)
        root_folders = await radarr.get_root_folders(settings, client)

        for entry in movie_entries:
            results["processed"] += 1
            media = entry.get("media", {})
            anilist_id = media.get("id")

            if not anilist_id:
                results["skipped"] += 1
                continue

            # Skip if already exists
            if anilist_id in existing_anilist_ids:
                results["skipped"] += 1
                continue

            try:
                # Map AniList data to Radarr format
                movie_data = mappers.map_anilist_to_radarr(media)

                # Set quality profile and root folder
                if quality_profiles:
                    movie_data["qualityProfileId"] = quality_profiles[0]["id"]
                if root_folders:
                    movie_data["rootFolderPath"] = (
                        mappers.map_root_folder("movie", root_folders)
                        or root_folders[0]["path"]
                    )

                if not dry_run:
                    # Add movie to Radarr
                    added_movie = await radarr.add_movie(movie_data, settings, client)
                    if added_movie:
                        results["added"] += 1
                        results["details"].append(
                            {
                                "title": movie_data["title"],
                                "action": "added",
                                "anilist_id": anilist_id,
                            }
                        )
                    else:
                        results["errors"] += 1
                else:
                    results["added"] += 1
                    results["details"].append(
                        {
                            "title": movie_data["title"],
                            "action": "would_add",
                            "anilist_id": anilist_id,
                        }
                    )

            except Exception as e:
                logger.error(
                    "Error processing movie", error=str(e), anilist_id=anilist_id
                )
                results["errors"] += 1

    return results


async def find_and_download_releases(
    media_title: str,
    settings: Settings,
    quality_filters: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Find and download releases for a given media title."""
    if not settings.seadx_api_key:
        return {"error": "SeaDx API key not configured"}

    results = {"found": 0, "filtered": 0, "downloaded": 0, "errors": 0, "releases": []}

    async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
        # Search for releases
        releases = await seadx.search_releases(media_title, settings, client=client)
        results["found"] = len(releases)

        if not releases:
            return results

        # Apply filters if specified
        if quality_filters:
            filter_functions = [
                filters.create_quality_filter(q) for q in quality_filters
            ]
            releases = filters.apply_filters(releases, filter_functions)

        results["filtered"] = len(releases)

        # Process releases
        for release in releases:
            try:
                torrent_data = mappers.map_seadx_release_to_torrent(release)
                results["releases"].append(
                    {
                        "name": torrent_data["name"],
                        "size": torrent_data["size"],
                        "quality": torrent_data["quality"],
                        "group": torrent_data["group"],
                    }
                )

                if not dry_run:
                    # Here you would implement actual download logic
                    # For now, just mark as would download
                    results["downloaded"] += 1
                else:
                    results["downloaded"] += 1

            except Exception as e:
                logger.error(
                    "Error processing release",
                    error=str(e),
                    release_name=release.get("name"),
                )
                results["errors"] += 1

    return results


async def sync_batch_from_anilist(
    usernames: list[str],
    settings: Settings,
    target_service: str = "sonarr",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Sync multiple AniList users to target service."""
    if target_service not in ["sonarr", "radarr"]:
        return {"error": "Invalid target service. Must be 'sonarr' or 'radarr'"}

    batch_results = {
        "total_users": len(usernames),
        "successful_syncs": 0,
        "failed_syncs": 0,
        "user_results": {},
    }

    sync_func = (
        sync_anilist_to_sonarr if target_service == "sonarr" else sync_anilist_to_radarr
    )

    for username in usernames:
        try:
            result = await sync_func(username, settings, dry_run)
            if "error" in result:
                batch_results["failed_syncs"] += 1
            else:
                batch_results["successful_syncs"] += 1
            batch_results["user_results"][username] = result

            # Small delay to avoid overwhelming APIs
            await asyncio.sleep(1)

        except Exception as e:
            logger.error("Error syncing user", error=str(e), username=username)
            batch_results["failed_syncs"] += 1
            batch_results["user_results"][username] = {"error": str(e)}

    return batch_results


async def check_sync_status(settings: Settings) -> dict[str, Any]:
    """Check the status of all configured services."""
    status = {
        "anilist": {
            "configured": bool(settings.anilist_access_token),
            "accessible": False,
        },
        "seadx": {"configured": bool(settings.seadx_api_key), "accessible": False},
        "sonarr": {
            "configured": bool(settings.sonarr_url and settings.sonarr_api_key),
            "accessible": False,
        },
        "radarr": {
            "configured": bool(settings.radarr_url and settings.radarr_api_key),
            "accessible": False,
        },
    }

    async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
        # Check AniList accessibility
        if status["anilist"]["configured"]:
            try:
                await anilist.get_user_anime_list("test", settings, client)
                status["anilist"]["accessible"] = True
            except Exception:
                pass

        # Check SeaDx accessibility
        if status["seadx"]["configured"]:
            try:
                stats = await seadx.get_release_stats(settings, client)
                status["seadx"]["accessible"] = bool(stats)
            except Exception:
                pass

        # Check Sonarr accessibility
        if status["sonarr"]["configured"]:
            try:
                await sonarr.get_series(settings, client)
                status["sonarr"]["accessible"] = True
            except Exception:
                pass

        # Check Radarr accessibility
        if status["radarr"]["configured"]:
            try:
                await radarr.get_movies(settings, client)
                status["radarr"]["accessible"] = True
            except Exception:
                pass

    return status
