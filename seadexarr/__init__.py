"""
SeaDexArr - SeaDx Starr Sync

A functional, modern Python application for syncing anime from AniList to Sonarr/Radarr.
"""

import warnings

from . import cli, clients, config, core, utils

__version__ = "0.6.0"
__all__ = ["cli", "clients", "config", "core", "utils"]


# Backward compatibility stubs for legacy classes
class SeaDexSonarr:
    """
    DEPRECATED: Legacy SeaDexSonarr class.

    Use the new CLI instead: seadexarr sync sonarr <username>
    """

    def __init__(self, *args, **kwargs):
        warnings.warn(
            "SeaDexSonarr is deprecated. Use the new CLI: 'seadexarr sync sonarr <username>'",
            DeprecationWarning,
            stacklevel=2,
        )

    def run(self):
        raise RuntimeError(
            "SeaDexSonarr.run() is deprecated. Use the new CLI: 'seadexarr sync sonarr <username>'"
        )


class SeaDexRadarr:
    """
    DEPRECATED: Legacy SeaDexRadarr class.

    Use the new CLI instead: seadexarr sync radarr <username>
    """

    def __init__(self, *args, **kwargs):
        warnings.warn(
            "SeaDexRadarr is deprecated. Use the new CLI: 'seadexarr sync radarr <username>'",
            DeprecationWarning,
            stacklevel=2,
        )

    def run(self):
        raise RuntimeError(
            "SeaDexRadarr.run() is deprecated. Use the new CLI: 'seadexarr sync radarr <username>'"
        )


def setup_logger(*args, **kwargs):
    """
    DEPRECATED: Legacy setup_logger function.

    Logging is now handled automatically by the CLI.
    """
    warnings.warn(
        "setup_logger() is deprecated. Logging is now handled automatically by the CLI.",
        DeprecationWarning,
        stacklevel=2,
    )
    # Return a basic logger to avoid breaking existing code
    import logging

    return logging.getLogger(__name__)


# Add legacy classes to __all__ for backward compatibility
__all__.extend(["SeaDexRadarr", "SeaDexSonarr", "setup_logger"])
