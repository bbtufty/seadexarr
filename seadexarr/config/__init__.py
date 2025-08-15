"""
Configuration management for SeaDexArr.

Minimal Pydantic BaseSettings for environment-based configuration.
"""

from .settings import Settings, get_settings

__all__ = ["Settings", "get_settings"]
