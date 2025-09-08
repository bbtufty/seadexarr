from importlib.metadata import version

# Get the version
__version__ = version(__name__)

from .modules import seadexarr_cli, SeaDexRadarr, SeaDexSonarr, setup_logger

__all__ = [
    "seadexarr_cli",
    "SeaDexRadarr",
    "SeaDexSonarr",
    "setup_logger",
]
