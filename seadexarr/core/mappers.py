"""
Mapping functions for SeaDexArr.

Pure functions for transforming data between different API formats.
"""

from typing import Any


def map_anilist_to_sonarr(anilist_media: dict[str, Any]) -> dict[str, Any]:
    """Map AniList media data to Sonarr series format."""
    title_data = anilist_media.get("title", {})

    # Prefer English title, fall back to romaji, then native
    title = (
        title_data.get("english")
        or title_data.get("romaji")
        or title_data.get("native")
        or "Unknown Title"
    )

    start_date = anilist_media.get("startDate", {})
    year = start_date.get("year")

    return {
        "title": title,
        "year": year,
        "tvdbId": None,  # Will need to be resolved separately
        "qualityProfileId": 1,  # Default, should be configurable
        "languageProfileId": 1,  # Default, should be configurable
        "rootFolderPath": "/tv/",  # Default, should be configurable
        "monitored": True,
        "seasonFolder": True,
        "addOptions": {
            "ignoreEpisodesWithFiles": False,
            "ignoreEpisodesWithoutFiles": False,
            "searchForMissingEpisodes": True,
        },
        "tags": [],
        "anilistId": anilist_media.get("id"),
        "genres": anilist_media.get("genres", []),
        "status": map_anilist_status_to_sonarr(anilist_media.get("status")),
        "episodes": anilist_media.get("episodes"),
        "format": anilist_media.get("format"),
    }


def map_anilist_to_radarr(anilist_media: dict[str, Any]) -> dict[str, Any]:
    """Map AniList media data to Radarr movie format."""
    title_data = anilist_media.get("title", {})

    title = (
        title_data.get("english")
        or title_data.get("romaji")
        or title_data.get("native")
        or "Unknown Title"
    )

    start_date = anilist_media.get("startDate", {})
    year = start_date.get("year")

    return {
        "title": title,
        "year": year,
        "tmdbId": None,  # Will need to be resolved separately
        "qualityProfileId": 1,  # Default, should be configurable
        "rootFolderPath": "/movies/",  # Default, should be configurable
        "monitored": True,
        "minimumAvailability": "announced",
        "tags": [],
        "addOptions": {"searchForMovie": True},
        "anilistId": anilist_media.get("id"),
        "genres": anilist_media.get("genres", []),
        "status": map_anilist_status_to_radarr(anilist_media.get("status")),
        "format": anilist_media.get("format"),
    }


def map_anilist_status_to_sonarr(anilist_status: str | None) -> str:
    """Map AniList status to Sonarr series status."""
    status_map = {
        "FINISHED": "ended",
        "RELEASING": "continuing",
        "NOT_YET_RELEASED": "tba",
        "CANCELLED": "ended",
        "HIATUS": "continuing",
    }

    return status_map.get(anilist_status, "tba")


def map_anilist_status_to_radarr(anilist_status: str | None) -> str:
    """Map AniList status to Radarr movie status."""
    status_map = {
        "FINISHED": "released",
        "RELEASING": "inCinemas",
        "NOT_YET_RELEASED": "announced",
        "CANCELLED": "deleted",
        "HIATUS": "inCinemas",
    }

    return status_map.get(anilist_status, "announced")


def map_seadx_release_to_torrent(seadx_release: dict[str, Any]) -> dict[str, Any]:
    """Map SeaDx release data to torrent information."""
    return {
        "name": seadx_release.get("name", ""),
        "hash": seadx_release.get("info_hash", ""),
        "magnet": seadx_release.get("magnet_link", ""),
        "size": seadx_release.get("size", 0),
        "seeders": seadx_release.get("seeders", 0),
        "leechers": seadx_release.get("leechers", 0),
        "category": seadx_release.get("category", ""),
        "upload_date": seadx_release.get("upload_date"),
        "group": extract_group_from_name(seadx_release.get("name", "")),
        "quality": extract_quality_from_name(seadx_release.get("name", "")),
        "source": extract_source_from_name(seadx_release.get("name", "")),
        "resolution": extract_resolution_from_name(seadx_release.get("name", "")),
    }


def extract_group_from_name(release_name: str) -> str:
    """Extract release group from torrent name."""
    if not release_name:
        return ""

    # Look for group name in brackets at the end
    if release_name.endswith("]"):
        start_bracket = release_name.rfind("[")
        if start_bracket != -1:
            return release_name[start_bracket + 1 : -1]

    # Look for group name after dash
    parts = release_name.split("-")
    if len(parts) > 1:
        potential_group = parts[-1].strip()
        # Basic validation - group names are usually short
        if len(potential_group) <= 20 and " " not in potential_group:
            return potential_group

    return ""


def extract_quality_from_name(release_name: str) -> str:
    """Extract quality information from torrent name."""
    if not release_name:
        return ""

    name_upper = release_name.upper()

    quality_indicators = [
        "REMUX",
        "BLURAY",
        "BD",
        "WEB-DL",
        "WEBDL",
        "WEBRIP",
        "HDTV",
        "PDTV",
        "DVDRIP",
        "BRRIP",
        "HDRIP",
    ]

    for quality in quality_indicators:
        if quality in name_upper:
            return quality.lower()

    return ""


def extract_source_from_name(release_name: str) -> str:
    """Extract source information from torrent name."""
    if not release_name:
        return ""

    name_upper = release_name.upper()

    source_indicators = [
        "BLURAY",
        "BD",
        "WEB",
        "HDTV",
        "PDTV",
        "DVD",
        "CAM",
        "TS",
        "TC",
    ]

    for source in source_indicators:
        if source in name_upper:
            return source.lower()

    return ""


def extract_resolution_from_name(release_name: str) -> str:
    """Extract resolution information from torrent name."""
    if not release_name:
        return ""

    name_upper = release_name.upper()

    resolution_indicators = ["2160P", "1080P", "720P", "480P", "4K", "UHD", "FHD", "HD"]

    for resolution in resolution_indicators:
        if resolution in name_upper:
            return resolution.lower()

    return ""


def normalize_title_for_matching(title: str) -> str:
    """Normalize title for better matching between services."""
    if not title:
        return ""

    # Convert to lowercase
    normalized = title.lower()

    # Remove common punctuation and special characters
    import re

    normalized = re.sub(r"[^\w\s]", " ", normalized)

    # Replace multiple spaces with single space
    normalized = re.sub(r"\s+", " ", normalized)

    # Remove common words that cause matching issues
    common_words = [
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
    ]
    words = normalized.split()
    filtered_words = [word for word in words if word not in common_words]

    return " ".join(filtered_words).strip()


def create_search_variants(title: str) -> list[str]:
    """Create search variants for better title matching."""
    if not title:
        return []

    variants = [title]

    # Add normalized version
    normalized = normalize_title_for_matching(title)
    if normalized and normalized != title.lower():
        variants.append(normalized)

    # Remove year from title if present
    import re

    no_year = re.sub(r"\s*\(\d{4}\)\s*", "", title)
    if no_year != title:
        variants.append(no_year)

    # Remove season/episode indicators
    no_season = re.sub(r"\s*(season|s)\s*\d+.*", "", title, flags=re.IGNORECASE)
    if no_season != title:
        variants.append(no_season)

    return list(set(variants))  # Remove duplicates


def map_quality_profile(
    quality_name: str, available_profiles: list[dict[str, Any]]
) -> int | None:
    """Map quality name to quality profile ID."""
    if not quality_name or not available_profiles:
        return None

    quality_lower = quality_name.lower()

    # Direct name match
    for profile in available_profiles:
        if profile.get("name", "").lower() == quality_lower:
            return profile.get("id")

    # Partial match
    for profile in available_profiles:
        profile_name = profile.get("name", "").lower()
        if quality_lower in profile_name or profile_name in quality_lower:
            return profile.get("id")

    return None


def map_root_folder(
    media_type: str, available_folders: list[dict[str, Any]]
) -> str | None:
    """Map media type to appropriate root folder."""
    if not available_folders:
        return None

    # For anime, prefer folders with anime in the name
    if media_type.lower() in ["anime", "tv", "series"]:
        for folder in available_folders:
            path = folder.get("path", "").lower()
            if "anime" in path or "tv" in path or "series" in path:
                return folder.get("path")

    # For movies
    if media_type.lower() == "movie":
        for folder in available_folders:
            path = folder.get("path", "").lower()
            if "movie" in path or "film" in path:
                return folder.get("path")

    # Default to first available folder
    return available_folders[0].get("path") if available_folders else None
