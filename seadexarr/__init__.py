from importlib.metadata import version

# Get the version
__version__ = version(__name__)

from .modules import SeaDexRadarr, SeaDexSonarr

__all__ = [
    "SeaDexRadarr",
    "SeaDexSonarr",
]
