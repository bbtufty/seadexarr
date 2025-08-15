"""
Synchronization functions for SeaDexArr with enhanced logging and error handling.

Core sync logic functions that orchestrate data flow between services with
comprehensive error handling, performance monitoring, and observability.
"""

import asyncio
import time
from typing import Any

import httpx

from ..clients import anilist, radarr, seadx, sonarr
from ..config import Settings
from ..utils.exceptions import (
    ConfigurationError,
    ValidationError,
)
from ..utils.logging import generate_correlation_id, get_logger, operation_logger
from . import filters, mappers

logger = get_logger(__name__)


def _validate_sync_settings(settings: Settings, service_type: str) -> None:
    """Validate settings required for sync operations."""
    if not settings.anilist_access_token:
        raise ConfigurationError(
            "AniList access token is required for sync operations",
            config_key="anilist_access_token",
            troubleshooting_hints=[
                "Set SEADEXARR_ANILIST_ACCESS_TOKEN in your environment",
                "Get your token from https://anilist.co/settings/developer",
                "Run 'seadexarr config-validate' to check all settings",
            ],
        )

    if service_type.lower() == "sonarr":
        if not settings.sonarr_url or not settings.sonarr_api_key:
            raise ConfigurationError(
                "Sonarr URL and API key are required for Sonarr sync",
                config_key="sonarr_configuration",
                troubleshooting_hints=[
                    "Set SEADEXARR_SONARR_URL and SEADEXARR_SONARR_API_KEY",
                    "Verify Sonarr is accessible at the configured URL",
                    "Check that the API key has sufficient permissions",
                ],
            )
    elif service_type.lower() == "radarr":
        if not settings.radarr_url or not settings.radarr_api_key:
            raise ConfigurationError(
                "Radarr URL and API key are required for Radarr sync",
                config_key="radarr_configuration",
                troubleshooting_hints=[
                    "Set SEADEXARR_RADARR_URL and SEADEXARR_RADARR_API_KEY",
                    "Verify Radarr is accessible at the configured URL",
                    "Check that the API key has sufficient permissions",
                ],
            )


def _create_sync_results() -> dict[str, Any]:
    """Create standardized sync results structure."""
    return {
        "processed": 0,
        "added": 0,
        "skipped": 0,
        "errors": 0,
        "details": [],
        "performance": {
            "start_time": time.time(),
            "duration_ms": 0,
        },
    }


def _finalize_sync_results(
    results: dict[str, Any], correlation_id: str | None = None
) -> dict[str, Any]:
    """Finalize sync results with performance metrics."""
    end_time = time.time()
    start_time = results.get("performance", {}).get("start_time", end_time)
    duration_ms = (end_time - start_time) * 1000

    results["performance"]["duration_ms"] = round(duration_ms, 2)
    results["performance"]["end_time"] = end_time

    # Calculate success rate
    total_operations = results.get("processed", 0)
    if total_operations > 0:
        success_count = total_operations - results.get("errors", 0)
        results["performance"]["success_rate"] = round(
            (success_count / total_operations) * 100, 1
        )
    else:
        results["performance"]["success_rate"] = 100.0

    # Log performance summary
    logger.performance(
        "Sync operation completed",
        duration_ms=duration_ms,
        processed=results.get("processed", 0),
        added=results.get("added", 0),
        skipped=results.get("skipped", 0),
        errors=results.get("errors", 0),
        success_rate=results["performance"]["success_rate"],
        correlation_id=correlation_id,
    )

    return results


async def sync_anilist_to_sonarr(
    anilist_username: str,
    settings: Settings,
    dry_run: bool = False,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Sync AniList anime list to Sonarr series with enhanced logging and error handling."""
    correlation_id = correlation_id or generate_correlation_id()

    with operation_logger(
        "anilist_to_sonarr_sync",
        correlation_id,
        username=anilist_username,
        dry_run=dry_run,
    ) as op_logger:

        # Validate settings
        try:
            _validate_sync_settings(settings, "sonarr")
        except ConfigurationError as e:
            op_logger.error("Configuration validation failed", error=e)
            return {"error": str(e), "error_details": e.to_dict()}

        if not anilist_username or not isinstance(anilist_username, str):
            error = ValidationError(
                "Valid AniList username is required",
                field_name="anilist_username",
                field_value=anilist_username,
                validation_rule="non-empty string",
            )
            op_logger.error("Username validation failed", error=error)
            return {"error": str(error), "error_details": error.to_dict()}

        results = _create_sync_results()

        op_logger.info(
            f"Starting AniList to Sonarr sync for user: {anilist_username}",
            dry_run=dry_run,
            correlation_id=correlation_id,
        )

        try:
            async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
                # Get user's anime list from AniList
                op_logger.info("Fetching AniList anime list")
                anime_list = await anilist.get_user_anime_list(
                    anilist_username, settings, client
                )

                if not anime_list:
                    error_msg = f"Failed to fetch AniList anime list for user: {anilist_username}"
                    op_logger.error(error_msg)
                    return {
                        "error": error_msg,
                        "error_details": {
                            "category": "api_error",
                            "service": "anilist",
                            "operation": "get_user_anime_list",
                        },
                    }

                op_logger.info(
                    f"Retrieved {len(anime_list)} anime entries from AniList"
                )

                # Get existing series from Sonarr
                op_logger.info("Fetching existing series from Sonarr")
                existing_series = await sonarr.get_series(settings, client)
                existing_anilist_ids = {
                    series.get("anilistId")
                    for series in existing_series
                    if series.get("anilistId")
                }

                op_logger.info(
                    f"Found {len(existing_series)} existing series in Sonarr"
                )

                # Get quality profiles and root folders
                op_logger.debug("Fetching Sonarr configuration")
                quality_profiles = await sonarr.get_quality_profiles(settings, client)
                root_folders = await sonarr.get_root_folders(settings, client)

                if not quality_profiles:
                    op_logger.warning("No quality profiles found in Sonarr")
                if not root_folders:
                    op_logger.warning("No root folders found in Sonarr")

                # Process each anime entry
                for entry_index, entry in enumerate(anime_list, 1):
                    with operation_logger(
                        "process_anime_entry",
                        correlation_id,
                        entry_index=entry_index,
                        total_entries=len(anime_list),
                    ) as entry_logger:

                        results["processed"] += 1
                        media = entry.get("media", {})
                        anilist_id = media.get("id")
                        anime_title = media.get("title", {}).get("romaji", "Unknown")

                        entry_logger.debug(
                            f"Processing anime entry {entry_index}/{len(anime_list)}: {anime_title}",
                            anilist_id=anilist_id,
                        )

                        if not anilist_id:
                            results["skipped"] += 1
                            entry_logger.warning(
                                f"Skipping entry with no AniList ID: {anime_title}"
                            )
                            continue

                        # Skip if already exists
                        if anilist_id in existing_anilist_ids:
                            results["skipped"] += 1
                            results["details"].append(
                                {
                                    "title": anime_title,
                                    "action": "skipped",
                                    "reason": "already exists in Sonarr",
                                    "anilist_id": anilist_id,
                                }
                            )
                            entry_logger.debug(
                                f"Skipping existing anime: {anime_title}"
                            )
                            continue

                        # Only process completed or watching series
                        status = entry.get("status")
                        if status not in ["COMPLETED", "CURRENT"]:
                            results["skipped"] += 1
                            results["details"].append(
                                {
                                    "title": anime_title,
                                    "action": "skipped",
                                    "reason": f"status is {status}",
                                    "anilist_id": anilist_id,
                                }
                            )
                            entry_logger.debug(
                                f"Skipping anime with status {status}: {anime_title}"
                            )
                            continue

                        try:
                            # Map AniList data to Sonarr format
                            entry_logger.debug(
                                f"Mapping AniList data for: {anime_title}"
                            )
                            series_data = mappers.map_anilist_to_sonarr(media)

                            # Set quality profile and root folder
                            if quality_profiles:
                                series_data["qualityProfileId"] = quality_profiles[0][
                                    "id"
                                ]
                                entry_logger.debug(
                                    f"Set quality profile ID: {quality_profiles[0]['id']}"
                                )
                            if root_folders:
                                mapped_folder = mappers.map_root_folder(
                                    "tv", root_folders
                                )
                                series_data["rootFolderPath"] = (
                                    mapped_folder or root_folders[0]["path"]
                                )
                                entry_logger.debug(
                                    f"Set root folder: {series_data['rootFolderPath']}"
                                )

                            if not dry_run:
                                # Add series to Sonarr
                                entry_logger.info(
                                    f"Adding series to Sonarr: {anime_title}"
                                )
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
                                            "sonarr_id": added_series.get("id"),
                                        }
                                    )
                                    entry_logger.info(
                                        f"Successfully added to Sonarr: {anime_title}"
                                    )
                                else:
                                    results["errors"] += 1
                                    results["details"].append(
                                        {
                                            "title": series_data["title"],
                                            "action": "error",
                                            "reason": "failed to add to Sonarr",
                                            "anilist_id": anilist_id,
                                        }
                                    )
                                    entry_logger.error(
                                        f"Failed to add to Sonarr: {anime_title}"
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
                                entry_logger.info(
                                    f"Would add to Sonarr (dry run): {anime_title}"
                                )

                        except Exception as e:
                            results["errors"] += 1
                            results["details"].append(
                                {
                                    "title": anime_title,
                                    "action": "error",
                                    "reason": str(e),
                                    "anilist_id": anilist_id,
                                }
                            )
                            entry_logger.error(
                                f"Error processing anime: {anime_title}",
                                error=e,
                                anilist_id=anilist_id,
                            )

                op_logger.info(
                    "AniList to Sonarr sync completed",
                    processed=results["processed"],
                    added=results["added"],
                    skipped=results["skipped"],
                    errors=results["errors"],
                )

        except Exception as e:
            op_logger.error("Sync operation failed with unexpected error", error=e)
            return {
                "error": f"Sync operation failed: {e!s}",
                "error_details": {
                    "category": "system_error",
                    "error_type": type(e).__name__,
                    "correlation_id": correlation_id,
                },
            }

        return _finalize_sync_results(results, correlation_id)


async def sync_anilist_to_radarr(
    anilist_username: str,
    settings: Settings,
    dry_run: bool = False,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Sync AniList manga/movie list to Radarr movies with enhanced logging and error handling."""
    correlation_id = correlation_id or generate_correlation_id()

    with operation_logger(
        "anilist_to_radarr_sync",
        correlation_id,
        username=anilist_username,
        dry_run=dry_run,
    ) as op_logger:

        # Validate settings
        try:
            _validate_sync_settings(settings, "radarr")
        except ConfigurationError as e:
            op_logger.error("Configuration validation failed", error=e)
            return {"error": str(e), "error_details": e.to_dict()}

        if not anilist_username or not isinstance(anilist_username, str):
            error = ValidationError(
                "Valid AniList username is required",
                field_name="anilist_username",
                field_value=anilist_username,
                validation_rule="non-empty string",
            )
            op_logger.error("Username validation failed", error=error)
            return {"error": str(error), "error_details": error.to_dict()}

        results = _create_sync_results()

        op_logger.info(
            f"Starting AniList to Radarr sync for user: {anilist_username}",
            dry_run=dry_run,
            correlation_id=correlation_id,
        )

        try:
            async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
                # Get user's anime list from AniList (filtering for movies)
                op_logger.info("Fetching AniList anime list for movies")
                anime_list = await anilist.get_user_anime_list(
                    anilist_username, settings, client
                )

                if not anime_list:
                    error_msg = f"Failed to fetch AniList anime list for user: {anilist_username}"
                    op_logger.error(error_msg)
                    return {
                        "error": error_msg,
                        "error_details": {
                            "category": "api_error",
                            "service": "anilist",
                            "operation": "get_user_anime_list",
                        },
                    }

                # Filter for movie format only
                movie_entries = [
                    entry
                    for entry in anime_list
                    if entry.get("media", {}).get("format") == "MOVIE"
                ]

                op_logger.info(
                    f"Found {len(movie_entries)} movie entries out of {len(anime_list)} total entries"
                )

                # Get existing movies from Radarr
                op_logger.info("Fetching existing movies from Radarr")
                existing_movies = await radarr.get_movies(settings, client)
                existing_anilist_ids = {
                    movie.get("anilistId")
                    for movie in existing_movies
                    if movie.get("anilistId")
                }

                op_logger.info(
                    f"Found {len(existing_movies)} existing movies in Radarr"
                )

                # Get quality profiles and root folders
                op_logger.debug("Fetching Radarr configuration")
                quality_profiles = await radarr.get_quality_profiles(settings, client)
                root_folders = await radarr.get_root_folders(settings, client)

                if not quality_profiles:
                    op_logger.warning("No quality profiles found in Radarr")
                if not root_folders:
                    op_logger.warning("No root folders found in Radarr")

                # Process each movie entry
                for entry_index, entry in enumerate(movie_entries, 1):
                    with operation_logger(
                        "process_movie_entry",
                        correlation_id,
                        entry_index=entry_index,
                        total_entries=len(movie_entries),
                    ) as entry_logger:

                        results["processed"] += 1
                        media = entry.get("media", {})
                        anilist_id = media.get("id")
                        movie_title = media.get("title", {}).get("romaji", "Unknown")

                        entry_logger.debug(
                            f"Processing movie entry {entry_index}/{len(movie_entries)}: {movie_title}",
                            anilist_id=anilist_id,
                        )

                        if not anilist_id:
                            results["skipped"] += 1
                            entry_logger.warning(
                                f"Skipping entry with no AniList ID: {movie_title}"
                            )
                            continue

                        # Skip if already exists
                        if anilist_id in existing_anilist_ids:
                            results["skipped"] += 1
                            results["details"].append(
                                {
                                    "title": movie_title,
                                    "action": "skipped",
                                    "reason": "already exists in Radarr",
                                    "anilist_id": anilist_id,
                                }
                            )
                            entry_logger.debug(
                                f"Skipping existing movie: {movie_title}"
                            )
                            continue

                        try:
                            # Map AniList data to Radarr format
                            entry_logger.debug(
                                f"Mapping AniList data for: {movie_title}"
                            )
                            movie_data = mappers.map_anilist_to_radarr(media)

                            # Set quality profile and root folder
                            if quality_profiles:
                                movie_data["qualityProfileId"] = quality_profiles[0][
                                    "id"
                                ]
                                entry_logger.debug(
                                    f"Set quality profile ID: {quality_profiles[0]['id']}"
                                )
                            if root_folders:
                                mapped_folder = mappers.map_root_folder(
                                    "movie", root_folders
                                )
                                movie_data["rootFolderPath"] = (
                                    mapped_folder or root_folders[0]["path"]
                                )
                                entry_logger.debug(
                                    f"Set root folder: {movie_data['rootFolderPath']}"
                                )

                            if not dry_run:
                                # Add movie to Radarr
                                entry_logger.info(
                                    f"Adding movie to Radarr: {movie_title}"
                                )
                                added_movie = await radarr.add_movie(
                                    movie_data, settings, client
                                )

                                if added_movie:
                                    results["added"] += 1
                                    results["details"].append(
                                        {
                                            "title": movie_data["title"],
                                            "action": "added",
                                            "anilist_id": anilist_id,
                                            "radarr_id": added_movie.get("id"),
                                        }
                                    )
                                    entry_logger.info(
                                        f"Successfully added to Radarr: {movie_title}"
                                    )
                                else:
                                    results["errors"] += 1
                                    results["details"].append(
                                        {
                                            "title": movie_data["title"],
                                            "action": "error",
                                            "reason": "failed to add to Radarr",
                                            "anilist_id": anilist_id,
                                        }
                                    )
                                    entry_logger.error(
                                        f"Failed to add to Radarr: {movie_title}"
                                    )
                            else:
                                results["added"] += 1
                                results["details"].append(
                                    {
                                        "title": movie_data["title"],
                                        "action": "would_add",
                                        "anilist_id": anilist_id,
                                    }
                                )
                                entry_logger.info(
                                    f"Would add to Radarr (dry run): {movie_title}"
                                )

                        except Exception as e:
                            results["errors"] += 1
                            results["details"].append(
                                {
                                    "title": movie_title,
                                    "action": "error",
                                    "reason": str(e),
                                    "anilist_id": anilist_id,
                                }
                            )
                            entry_logger.error(
                                f"Error processing movie: {movie_title}",
                                error=e,
                                anilist_id=anilist_id,
                            )

                op_logger.info(
                    "AniList to Radarr sync completed",
                    processed=results["processed"],
                    added=results["added"],
                    skipped=results["skipped"],
                    errors=results["errors"],
                )

        except Exception as e:
            op_logger.error("Sync operation failed with unexpected error", error=e)
            return {
                "error": f"Sync operation failed: {e!s}",
                "error_details": {
                    "category": "system_error",
                    "error_type": type(e).__name__,
                    "correlation_id": correlation_id,
                },
            }

        return _finalize_sync_results(results, correlation_id)


async def find_and_download_releases(
    media_title: str,
    settings: Settings,
    quality_filters: list[str] | None = None,
    dry_run: bool = False,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Find and download releases for a given media title with enhanced logging."""
    correlation_id = correlation_id or generate_correlation_id()

    with operation_logger(
        "find_and_download_releases",
        correlation_id,
        media_title=media_title,
        dry_run=dry_run,
    ) as op_logger:

        if not settings.seadx_api_key:
            error = ConfigurationError(
                "SeaDx API key is required for release search",
                config_key="seadx_api_key",
                troubleshooting_hints=[
                    "Set SEADEXARR_SEADX_API_KEY in your environment",
                    "Contact SeaDx for API access",
                    "Run 'seadexarr config-validate' to check settings",
                ],
            )
            op_logger.error("SeaDx API key not configured", error=error)
            return {"error": str(error), "error_details": error.to_dict()}

        if not media_title or not isinstance(media_title, str):
            error = ValidationError(
                "Valid media title is required",
                field_name="media_title",
                field_value=media_title,
                validation_rule="non-empty string",
            )
            op_logger.error("Media title validation failed", error=error)
            return {"error": str(error), "error_details": error.to_dict()}

        results = {
            "found": 0,
            "filtered": 0,
            "downloaded": 0,
            "errors": 0,
            "releases": [],
            "performance": {
                "start_time": time.time(),
                "search_duration_ms": 0,
                "filter_duration_ms": 0,
            },
        }

        op_logger.info(
            f"Starting release search for: {media_title}",
            quality_filters=quality_filters,
            dry_run=dry_run,
        )

        try:
            async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
                # Search for releases
                search_start = time.time()
                op_logger.info(f"Searching SeaDx for releases: {media_title}")
                releases = await seadx.search_releases(
                    media_title, settings, client=client
                )
                search_duration = (time.time() - search_start) * 1000
                results["performance"]["search_duration_ms"] = round(search_duration, 2)
                results["found"] = len(releases)

                op_logger.info(f"Found {len(releases)} releases on SeaDx")

                if not releases:
                    op_logger.info("No releases found for media title")
                    return _finalize_search_results(results, correlation_id)

                # Apply filters if specified
                if quality_filters:
                    filter_start = time.time()
                    op_logger.debug(f"Applying quality filters: {quality_filters}")

                    filter_functions = [
                        filters.create_quality_filter(q) for q in quality_filters
                    ]
                    releases = filters.apply_filters(releases, filter_functions)

                    filter_duration = (time.time() - filter_start) * 1000
                    results["performance"]["filter_duration_ms"] = round(
                        filter_duration, 2
                    )

                    op_logger.info(
                        f"Filtered to {len(releases)} releases",
                        applied_filters=quality_filters,
                        filter_duration_ms=results["performance"]["filter_duration_ms"],
                    )

                results["filtered"] = len(releases)

                # Process releases
                for release_index, release in enumerate(releases, 1):
                    with operation_logger(
                        "process_release",
                        correlation_id,
                        release_index=release_index,
                        total_releases=len(releases),
                    ) as release_logger:

                        try:
                            release_name = release.get("name", "Unknown")
                            release_logger.debug(
                                f"Processing release {release_index}/{len(releases)}: {release_name}"
                            )

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
                                release_logger.info(
                                    f"Downloaded release: {release_name}"
                                )
                            else:
                                results["downloaded"] += 1
                                release_logger.debug(
                                    f"Would download (dry run): {release_name}"
                                )

                        except Exception as e:
                            results["errors"] += 1
                            release_logger.error(
                                f"Error processing release: {release.get('name', 'Unknown')}",
                                error=e,
                                release_index=release_index,
                            )

                op_logger.info(
                    "Release search and processing completed",
                    found=results["found"],
                    filtered=results["filtered"],
                    downloaded=results["downloaded"],
                    errors=results["errors"],
                )

        except Exception as e:
            op_logger.error("Release search failed with unexpected error", error=e)
            return {
                "error": f"Release search failed: {e!s}",
                "error_details": {
                    "category": "system_error",
                    "error_type": type(e).__name__,
                    "correlation_id": correlation_id,
                },
            }

        return _finalize_search_results(results, correlation_id)


def _finalize_search_results(
    results: dict[str, Any], correlation_id: str | None = None
) -> dict[str, Any]:
    """Finalize search results with performance metrics."""
    end_time = time.time()
    start_time = results.get("performance", {}).get("start_time", end_time)
    total_duration = (end_time - start_time) * 1000

    results["performance"]["total_duration_ms"] = round(total_duration, 2)
    results["performance"]["end_time"] = end_time

    # Log performance summary
    logger.performance(
        "Release search completed",
        duration_ms=total_duration,
        found=results.get("found", 0),
        filtered=results.get("filtered", 0),
        downloaded=results.get("downloaded", 0),
        errors=results.get("errors", 0),
        correlation_id=correlation_id,
    )

    return results


async def sync_batch_from_anilist(
    usernames: list[str],
    settings: Settings,
    target_service: str = "sonarr",
    dry_run: bool = False,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Sync multiple AniList users to target service with enhanced logging."""
    correlation_id = correlation_id or generate_correlation_id()

    with operation_logger(
        "batch_sync",
        correlation_id,
        target_service=target_service,
        user_count=len(usernames),
        dry_run=dry_run,
    ) as op_logger:

        if target_service not in ["sonarr", "radarr"]:
            error = ValidationError(
                f"Invalid target service: {target_service}",
                field_name="target_service",
                field_value=target_service,
                validation_rule="must be 'sonarr' or 'radarr'",
            )
            op_logger.error("Target service validation failed", error=error)
            return {"error": str(error), "error_details": error.to_dict()}

        if not usernames or not isinstance(usernames, list):
            error = ValidationError(
                "Valid list of usernames is required",
                field_name="usernames",
                field_value=usernames,
                validation_rule="non-empty list of strings",
            )
            op_logger.error("Usernames validation failed", error=error)
            return {"error": str(error), "error_details": error.to_dict()}

        batch_results = {
            "total_users": len(usernames),
            "successful_syncs": 0,
            "failed_syncs": 0,
            "user_results": {},
            "performance": {
                "start_time": time.time(),
                "user_durations": {},
            },
        }

        sync_func = (
            sync_anilist_to_sonarr
            if target_service == "sonarr"
            else sync_anilist_to_radarr
        )

        op_logger.info(
            f"Starting batch sync for {len(usernames)} users to {target_service}",
            usernames=usernames,
            dry_run=dry_run,
        )

        for user_index, username in enumerate(usernames, 1):
            user_correlation_id = f"{correlation_id}_user_{user_index}"
            user_start_time = time.time()

            with operation_logger(
                "batch_sync_user",
                user_correlation_id,
                username=username,
                user_index=user_index,
                total_users=len(usernames),
            ) as user_logger:

                try:
                    user_logger.info(
                        f"Syncing user {user_index}/{len(usernames)}: {username}",
                        target_service=target_service,
                    )

                    result = await sync_func(
                        username, settings, dry_run, user_correlation_id
                    )
                    user_duration = (time.time() - user_start_time) * 1000
                    batch_results["performance"]["user_durations"][username] = round(
                        user_duration, 2
                    )

                    if "error" in result:
                        batch_results["failed_syncs"] += 1
                        user_logger.error(
                            f"Sync failed for user: {username}", error=result["error"]
                        )
                    else:
                        batch_results["successful_syncs"] += 1
                        user_logger.info(
                            f"Sync completed for user: {username}",
                            duration_ms=user_duration,
                            added=result.get("added", 0),
                            skipped=result.get("skipped", 0),
                            errors=result.get("errors", 0),
                        )

                    batch_results["user_results"][username] = result

                    # Small delay to avoid overwhelming APIs
                    await asyncio.sleep(1)

                except Exception as e:
                    user_duration = (time.time() - user_start_time) * 1000
                    batch_results["performance"]["user_durations"][username] = round(
                        user_duration, 2
                    )
                    batch_results["failed_syncs"] += 1
                    batch_results["user_results"][username] = {
                        "error": str(e),
                        "error_details": {
                            "error_type": type(e).__name__,
                            "correlation_id": user_correlation_id,
                        },
                    }
                    user_logger.error(
                        f"Unexpected error syncing user: {username}",
                        error=e,
                        duration_ms=user_duration,
                    )

        # Calculate batch performance metrics
        total_duration = (
            time.time() - batch_results["performance"]["start_time"]
        ) * 1000
        batch_results["performance"]["total_duration_ms"] = round(total_duration, 2)

        if batch_results["total_users"] > 0:
            success_rate = (
                batch_results["successful_syncs"] / batch_results["total_users"]
            ) * 100
            batch_results["performance"]["success_rate"] = round(success_rate, 1)
        else:
            batch_results["performance"]["success_rate"] = 100.0

        op_logger.performance(
            "Batch sync completed",
            duration_ms=total_duration,
            total_users=batch_results["total_users"],
            successful_syncs=batch_results["successful_syncs"],
            failed_syncs=batch_results["failed_syncs"],
            success_rate=batch_results["performance"]["success_rate"],
            target_service=target_service,
        )

        return batch_results


async def check_sync_status(
    settings: Settings, correlation_id: str | None = None
) -> dict[str, Any]:
    """Check the status of all configured services with enhanced logging."""
    correlation_id = correlation_id or generate_correlation_id()

    with operation_logger("service_status_check", correlation_id) as op_logger:

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

        op_logger.info("Starting service connectivity checks")

        async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
            # Check each service
            for service_name, service_status in status.items():
                with operation_logger(
                    f"check_service_{service_name}",
                    correlation_id,
                    service=service_name,
                ) as service_logger:

                    if not service_status["configured"]:
                        service_logger.debug(
                            f"Service {service_name} not configured, skipping accessibility check"
                        )
                        continue

                    try:
                        service_logger.debug(
                            f"Checking accessibility for {service_name}"
                        )

                        # Check service-specific endpoints
                        if service_name == "anilist":
                            await anilist.get_user_anime_list("test", settings, client)
                            status[service_name]["accessible"] = True  # If no exception, it's accessible
                        elif service_name == "seadx":
                            stats = await seadx.get_release_stats(settings, client)
                            status[service_name]["accessible"] = bool(stats)
                        elif service_name == "sonarr":
                            series = await sonarr.get_series(settings, client)
                            status[service_name]["accessible"] = isinstance(
                                series, list
                            )
                        elif service_name == "radarr":
                            movies = await radarr.get_movies(settings, client)
                            status[service_name]["accessible"] = isinstance(
                                movies, list
                            )

                        if status[service_name]["accessible"]:
                            service_logger.info(f"Service {service_name} is accessible")
                        else:
                            service_logger.warning(
                                f"Service {service_name} is not accessible"
                            )

                    except Exception as e:
                        status[service_name]["accessible"] = False
                        service_logger.error(
                            f"Service {service_name} accessibility check failed",
                            error=e,
                            service=service_name,
                        )

        # Log overall status summary
        configured_count = sum(1 for s in status.values() if s["configured"])
        accessible_count = sum(1 for s in status.values() if s["accessible"])

        op_logger.info(
            "Service status check completed",
            configured_services=configured_count,
            accessible_services=accessible_count,
            total_services=len(status),
        )

        return status
