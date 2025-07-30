from importlib.metadata import version

# Get the version
__version__ = version(__name__)

from .modules import SeaDexRadarr, SeaDexSonarr, setup_logger

__all__ = [
    "SeaDexRadarr",
    "SeaDexSonarr",
    "setup_logger",
]
