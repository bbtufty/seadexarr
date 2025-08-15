"""
Application settings using Pydantic BaseSettings.

Minimal configuration management with environment variable support.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration settings."""

    # Logging configuration
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Log format: json or console")

    # SeaDx API configuration
    seadx_api_key: str | None = Field(default=None, description="SeaDx API key")
    seadx_base_url: str = Field(
        default="https://releases.seadx.org", description="SeaDx base URL"
    )

    # AniList configuration
    anilist_client_id: str | None = Field(default=None, description="AniList client ID")
    anilist_client_secret: str | None = Field(
        default=None, description="AniList client secret"
    )
    anilist_access_token: str | None = Field(
        default=None, description="AniList access token"
    )

    # Sonarr configuration
    sonarr_url: str | None = Field(default=None, description="Sonarr base URL")
    sonarr_api_key: str | None = Field(default=None, description="Sonarr API key")

    # Radarr configuration
    radarr_url: str | None = Field(default=None, description="Radarr base URL")
    radarr_api_key: str | None = Field(default=None, description="Radarr API key")

    # Torrent configuration
    qbittorrent_host: str | None = Field(
        default="localhost", description="qBittorrent host"
    )
    qbittorrent_port: int = Field(default=8080, description="qBittorrent port")
    qbittorrent_username: str | None = Field(
        default=None, description="qBittorrent username"
    )
    qbittorrent_password: str | None = Field(
        default=None, description="qBittorrent password"
    )

    # HTTP client configuration
    http_timeout: int = Field(default=30, description="HTTP request timeout in seconds")
    http_retries: int = Field(default=3, description="Number of HTTP retries")

    # Application configuration
    config_file: Path | None = Field(
        default=None, description="Path to configuration file"
    )
    dry_run: bool = Field(default=False, description="Dry run mode - no actual changes")

    model_config = {
        "env_prefix": "SEADEXARR_",
        "env_file": ".env",
        "case_sensitive": False,
    }


def get_settings() -> Settings:
    """Get application settings instance."""
    return Settings()
