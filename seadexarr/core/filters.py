"""
Filtering functions for SeaDexArr.

Pure functions for filtering media releases and content.
"""

from collections.abc import Callable
from typing import Any


def filter_by_quality(
    releases: list[dict[str, Any]], quality_filter: str
) -> list[dict[str, Any]]:
    """Filter releases by quality criteria."""
    if not quality_filter:
        return releases

    quality_lower = quality_filter.lower()

    return [
        release
        for release in releases
        if quality_lower in release.get("quality", "").lower()
        or quality_lower in release.get("resolution", "").lower()
    ]


def filter_by_size(
    releases: list[dict[str, Any]],
    min_size_gb: float | None = None,
    max_size_gb: float | None = None,
) -> list[dict[str, Any]]:
    """Filter releases by file size range."""
    if min_size_gb is None and max_size_gb is None:
        return releases

    def size_matches(release: dict[str, Any]) -> bool:
        size = release.get("size_bytes", 0)
        if size <= 0:
            return True  # Include if size unknown

        size_gb = size / (1024**3)  # Convert bytes to GB

        if min_size_gb is not None and size_gb < min_size_gb:
            return False
        if max_size_gb is not None and size_gb > max_size_gb:
            return False

        return True

    return [release for release in releases if size_matches(release)]


def filter_by_language(
    releases: list[dict[str, Any]], languages: list[str]
) -> list[dict[str, Any]]:
    """Filter releases by language preferences."""
    if not languages:
        return releases

    languages_lower = [lang.lower() for lang in languages]

    def language_matches(release: dict[str, Any]) -> bool:
        release_languages = release.get("languages", [])
        if not release_languages:
            return True  # Include if language unknown

        return any(lang.lower() in languages_lower for lang in release_languages)

    return [release for release in releases if language_matches(release)]


def filter_by_codec(
    releases: list[dict[str, Any]], preferred_codecs: list[str]
) -> list[dict[str, Any]]:
    """Filter releases by video codec preferences."""
    if not preferred_codecs:
        return releases

    codecs_lower = [codec.lower() for codec in preferred_codecs]

    def codec_matches(release: dict[str, Any]) -> bool:
        video_codec = release.get("video_codec", "").lower()
        if not video_codec:
            return True  # Include if codec unknown

        return any(codec in video_codec for codec in codecs_lower)

    return [release for release in releases if codec_matches(release)]


def filter_by_source(
    releases: list[dict[str, Any]], preferred_sources: list[str]
) -> list[dict[str, Any]]:
    """Filter releases by source type (BluRay, WEB-DL, etc.)."""
    if not preferred_sources:
        return releases

    sources_lower = [source.lower() for source in preferred_sources]

    def source_matches(release: dict[str, Any]) -> bool:
        source = release.get("source", "").lower()
        if not source:
            return True  # Include if source unknown

        return any(src in source for src in sources_lower)

    return [release for release in releases if source_matches(release)]


def filter_by_group(
    releases: list[dict[str, Any]],
    preferred_groups: list[str],
    excluded_groups: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Filter releases by release group preferences."""
    if not preferred_groups and not excluded_groups:
        return releases

    preferred_lower = (
        [group.lower() for group in preferred_groups] if preferred_groups else []
    )
    excluded_lower = (
        [group.lower() for group in excluded_groups] if excluded_groups else []
    )

    def group_matches(release: dict[str, Any]) -> bool:
        group = release.get("group", "").lower()

        # Exclude if in excluded list
        if excluded_lower and any(exc in group for exc in excluded_lower):
            return False

        # If preferred groups specified, must match one
        if preferred_lower:
            return any(pref in group for pref in preferred_lower)

        return True

    return [release for release in releases if group_matches(release)]


def filter_by_episode_range(
    releases: list[dict[str, Any]],
    min_episode: int | None = None,
    max_episode: int | None = None,
) -> list[dict[str, Any]]:
    """Filter releases by episode number range."""
    if min_episode is None and max_episode is None:
        return releases

    def episode_matches(release: dict[str, Any]) -> bool:
        episode = release.get("episode")
        if episode is None:
            return True  # Include if episode unknown

        try:
            ep_num = int(episode)
            if min_episode is not None and ep_num < min_episode:
                return False
            if max_episode is not None and ep_num > max_episode:
                return False
            return True
        except (ValueError, TypeError):
            return True  # Include if episode parsing fails

    return [release for release in releases if episode_matches(release)]


def filter_already_downloaded(
    releases: list[dict[str, Any]], existing_files: list[str]
) -> list[dict[str, Any]]:
    """Filter out releases that have already been downloaded."""
    if not existing_files:
        return releases

    existing_lower = [f.lower() for f in existing_files]

    def not_downloaded(release: dict[str, Any]) -> bool:
        filename = release.get("filename", "").lower()
        title = release.get("title", "").lower()

        return not any(
            existing in filename or existing in title for existing in existing_lower
        )

    return [release for release in releases if not_downloaded(release)]


def apply_filters(
    releases: list[dict[str, Any]],
    filters: list[Callable[[list[dict[str, Any]]], list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    """Apply a series of filter functions to releases."""
    result = releases
    for filter_func in filters:
        result = filter_func(result)
    return result


def create_quality_filter(
    quality: str,
) -> Callable[[list[dict[str, Any]]], list[dict[str, Any]]]:
    """Create a quality filter function."""
    return lambda releases: filter_by_quality(releases, quality)


def create_size_filter(
    min_size_gb: float | None = None, max_size_gb: float | None = None
) -> Callable[[list[dict[str, Any]]], list[dict[str, Any]]]:
    """Create a size filter function."""
    return lambda releases: filter_by_size(releases, min_size_gb, max_size_gb)


def create_language_filter(
    languages: list[str],
) -> Callable[[list[dict[str, Any]]], list[dict[str, Any]]]:
    """Create a language filter function."""
    return lambda releases: filter_by_language(releases, languages)
