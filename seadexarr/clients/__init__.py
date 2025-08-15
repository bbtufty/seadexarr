"""
HTTP client modules for external APIs.

Functional approach to client implementations with async functions.
"""

from . import anilist, radarr, seadx, sonarr

__all__ = ["anilist", "radarr", "seadx", "sonarr"]
