"""
SeaDexArr - SeaDx Starr Sync

A functional, modern Python application for syncing anime from AniList to Sonarr/Radarr.
"""

from . import cli, clients, config, core, utils

__version__ = "0.6.0"
__all__ = ["cli", "clients", "config", "core", "utils"]
