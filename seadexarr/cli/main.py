"""
Modern CLI interface for SeaDexArr using Typer.

Production-ready command-line interface with comprehensive async support,
Rich formatting, and proper error handling.
"""

import asyncio
import platform
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Table

from ..config import Settings, get_settings
from ..core import sync
from ..utils import logging
from ..utils.exceptions import SeaDexArrError

# Create the main Typer app with modern configuration
app = typer.Typer(
    name="seadexarr",
    help="[bold blue]SeaDx Starr Sync[/bold blue] - Synchronize anime from AniList to Sonarr/Radarr",
    epilog="Visit https://github.com/seadx/seadexarr for documentation and examples",
    no_args_is_help=True,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
)

# Create sync subcommand group
sync_app = typer.Typer(
    name="sync",
    help="Synchronization commands for media services",
    rich_markup_mode="rich",
)
app.add_typer(sync_app, name="sync")

# Create console for rich output
console = Console()

# Global settings
_settings: Settings | None = None


def get_configured_settings(config_path: Path | None = None) -> Settings:
    """Get configured settings with optional config file path."""
    global _settings
    if _settings is None or config_path is not None:
        if config_path and config_path.exists():
            # Load from specific config file if provided
            _settings = Settings(_env_file=str(config_path))
        else:
            _settings = get_settings()
    return _settings


def setup_logging_for_cli(
    verbose: bool = False, quiet: bool = False, format_type: str = "console"
) -> None:
    """Setup logging for CLI operations with proper levels."""
    if quiet:
        level = "ERROR"
    elif verbose:
        level = "DEBUG"
    else:
        level = "INFO"

    logging.configure_logging(log_level=level, log_format=format_type)


def display_error(message: str, exception: Exception | None = None) -> None:
    """Display error message with rich formatting."""
    if exception:
        console.print(f"[red]✗ Error:[/red] {message}")
        if isinstance(exception, SeaDexArrError):
            console.print(f"[dim red]Details: {exception}[/dim red]")
    else:
        console.print(f"[red]✗ Error:[/red] {message}")


def display_success(message: str) -> None:
    """Display success message with rich formatting."""
    console.print(f"[green]✓[/green] {message}")


def display_warning(message: str) -> None:
    """Display warning message with rich formatting."""
    console.print(f"[yellow]⚠[/yellow] {message}")


def display_sync_results(
    results: dict[str, Any], title: str, verbose: bool = False
) -> None:
    """Display sync results in a rich table format."""
    if "error" in results:
        display_error(results["error"])
        return

    # Main results table
    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan", min_width=12)
    table.add_column("Count", justify="right", style="green", min_width=8)
    table.add_column("Status", style="white", min_width=10)

    metrics = [
        ("Processed", results.get("processed", 0), "📊"),
        (
            "Added",
            results.get("added", 0),
            "✅" if results.get("added", 0) > 0 else "-",
        ),
        (
            "Skipped",
            results.get("skipped", 0),
            "⏭️" if results.get("skipped", 0) > 0 else "-",
        ),
        (
            "Errors",
            results.get("errors", 0),
            "❌" if results.get("errors", 0) > 0 else "✅",
        ),
    ]

    for metric, count, status in metrics:
        table.add_row(metric, str(count), status)

    console.print(table)

    # Detailed results if verbose
    if verbose and results.get("details"):
        console.print("\n[bold]Operation Details:[/bold]")

        for detail in results["details"]:
            action = detail.get("action", "unknown")
            title_text = detail.get("title", "Unknown")
            reason = detail.get("reason", "")

            action_colors = {
                "added": "green",
                "would_add": "yellow",
                "skipped": "blue",
                "error": "red",
            }
            color = action_colors.get(action, "white")

            # Format the action nicely
            action_display = action.replace("_", " ").title()
            console.print(f"  [{color}]{action_display}[/{color}]: {title_text}")

            if reason:
                console.print(f"    [dim]Reason: {reason}[/dim]")


async def run_with_progress(
    operation_name: str, operation_func, *args, show_spinner: bool = True
) -> Any:
    """Run an async operation with progress indicator."""
    if show_spinner:
        with console.status(f"[bold blue]{operation_name}..."):
            return await operation_func(*args)
    else:
        return await operation_func(*args)


@app.callback()
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose logging and output"
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Only show errors and critical messages"
    ),
    config: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Configuration file path (.env or YAML)",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    # Legacy compatibility options
    sonarr_user: str | None = typer.Option(
        None,
        "--sonarr",
        help="[dim](Legacy) Sync AniList user to Sonarr[/dim]",
        hidden=True,
    ),
    radarr_user: str | None = typer.Option(
        None,
        "--radarr",
        help="[dim](Legacy) Sync AniList user to Radarr[/dim]",
        hidden=True,
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview changes without applying them"
    ),
):
    """
    [bold blue]SeaDxArr[/bold blue] - Sync anime from AniList to Sonarr/Radarr

    A comprehensive tool for synchronizing your AniList anime/manga lists
    with Sonarr and Radarr media management systems.

    [bold]Examples:[/bold]
        seadexarr sync sonarr myusername --dry-run
        seadexarr sync-batch user1 user2 user3 --target=sonarr
        seadexarr status
        seadexarr config-validate
    """
    setup_logging_for_cli(verbose, quiet)

    # Store settings in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["settings"] = get_configured_settings(config)
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet
    ctx.obj["dry_run"] = dry_run

    # Handle legacy compatibility
    if sonarr_user:
        display_warning(
            "Using legacy --sonarr option. Consider using 'seadexarr sync sonarr' instead."
        )
        asyncio.run(
            legacy_sync_sonarr(sonarr_user, ctx.obj["settings"], dry_run, verbose)
        )
        raise typer.Exit()

    if radarr_user:
        display_warning(
            "Using legacy --radarr option. Consider using 'seadexarr sync radarr' instead."
        )
        asyncio.run(
            legacy_sync_radarr(radarr_user, ctx.obj["settings"], dry_run, verbose)
        )
        raise typer.Exit()


# --- Sync Commands ---


@sync_app.command("sonarr")
def sync_sonarr_command(
    ctx: typer.Context,
    username: str = typer.Argument(..., help="AniList username to sync"),
    dry_run: bool = typer.Option(
        None, "--dry-run", help="Preview changes without applying them"
    ),
    search_missing: bool = typer.Option(
        False, "--search-missing", help="Automatically search for missing episodes"
    ),
):
    """
    Sync AniList anime list to Sonarr series.

    Fetches the specified user's AniList anime list and adds new series
    to Sonarr, respecting quality profiles and root folder configurations.

    [bold]Examples:[/bold]
        seadexarr sync sonarr myusername
        seadexarr sync sonarr myusername --dry-run --verbose
    """
    settings = ctx.obj["settings"]
    verbose = ctx.obj["verbose"]
    is_dry_run = dry_run if dry_run is not None else ctx.obj["dry_run"]

    async def run_sync():
        operation_name = f"Syncing {username}'s AniList to Sonarr"
        if is_dry_run:
            operation_name += " (Dry Run)"

        result = await run_with_progress(
            operation_name, sync.sync_anilist_to_sonarr, username, settings, is_dry_run
        )

        display_sync_results(
            result, f"AniList → Sonarr Sync Results for {username}", verbose
        )

        if not is_dry_run and result.get("added", 0) > 0 and search_missing:
            display_success(
                f"Added {result['added']} series. Triggering search for missing episodes..."
            )

    try:
        asyncio.run(run_sync())
    except KeyboardInterrupt:
        display_warning("Operation cancelled by user")
        raise typer.Exit(130)
    except Exception as e:
        display_error("Sync operation failed", e)
        raise typer.Exit(1)


@sync_app.command("radarr")
def sync_radarr_command(
    ctx: typer.Context,
    username: str = typer.Argument(..., help="AniList username to sync"),
    dry_run: bool = typer.Option(
        None, "--dry-run", help="Preview changes without applying them"
    ),
    search_missing: bool = typer.Option(
        False, "--search-missing", help="Automatically search for missing movies"
    ),
):
    """
    Sync AniList movie list to Radarr movies.

    Fetches anime movies from the specified user's AniList and adds them
    to Radarr with appropriate quality profiles and root folders.

    [bold]Examples:[/bold]
        seadexarr sync radarr myusername
        seadexarr sync radarr myusername --dry-run
    """
    settings = ctx.obj["settings"]
    verbose = ctx.obj["verbose"]
    is_dry_run = dry_run if dry_run is not None else ctx.obj["dry_run"]

    async def run_sync():
        operation_name = f"Syncing {username}'s AniList movies to Radarr"
        if is_dry_run:
            operation_name += " (Dry Run)"

        result = await run_with_progress(
            operation_name, sync.sync_anilist_to_radarr, username, settings, is_dry_run
        )

        display_sync_results(
            result, f"AniList → Radarr Sync Results for {username}", verbose
        )

    try:
        asyncio.run(run_sync())
    except KeyboardInterrupt:
        display_warning("Operation cancelled by user")
        raise typer.Exit(130)
    except Exception as e:
        display_error("Sync operation failed", e)
        raise typer.Exit(1)


# --- Batch Sync Command ---


@app.command("sync-batch")
def sync_batch_command(
    ctx: typer.Context,
    usernames: list[str] = typer.Argument(..., help="AniList usernames to sync"),
    target: str = typer.Option(
        "sonarr", "--target", "-t", help="Target service: 'sonarr' or 'radarr'"
    ),
    dry_run: bool = typer.Option(
        None, "--dry-run", help="Preview changes without applying them"
    ),
    concurrent_limit: int = typer.Option(
        3, "--concurrent", help="Maximum concurrent syncs"
    ),
):
    """
    Sync multiple AniList users to Sonarr or Radarr.

    Processes multiple users concurrently with rate limiting to avoid
    overwhelming the APIs. Shows individual progress for each user.

    [bold]Examples:[/bold]
        seadexarr sync-batch user1 user2 user3 --target=sonarr
        seadexarr sync-batch user1 user2 --target=radarr --concurrent=2
    """
    if target not in ["sonarr", "radarr"]:
        display_error("Target must be 'sonarr' or 'radarr'")
        raise typer.Exit(1)

    settings = ctx.obj["settings"]
    verbose = ctx.obj["verbose"]
    is_dry_run = dry_run if dry_run is not None else ctx.obj["dry_run"]

    async def run_batch_sync():
        operation_name = f"Batch syncing {len(usernames)} users to {target.title()}"
        if is_dry_run:
            operation_name += " (Dry Run)"

        # Use progress bar for batch operations
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:

            task = progress.add_task(operation_name, total=len(usernames))

            result = await sync.sync_batch_from_anilist(
                usernames, settings, target, is_dry_run
            )

            progress.update(task, completed=len(usernames))

        # Display batch results
        table = Table(title=f"Batch Sync Results ({target.title()})", show_header=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Count", justify="right", style="green")
        table.add_column("Status", style="white")

        table.add_row("Total Users", str(result["total_users"]), "📊")
        table.add_row(
            "Successful",
            str(result["successful_syncs"]),
            "✅" if result["successful_syncs"] > 0 else "-",
        )
        table.add_row(
            "Failed",
            str(result["failed_syncs"]),
            "❌" if result["failed_syncs"] > 0 else "✅",
        )

        console.print(table)

        # Show per-user results if verbose
        if verbose:
            console.print("\n[bold]Individual User Results:[/bold]")
            for username, user_result in result["user_results"].items():
                if "error" in user_result:
                    console.print(f"  [red]❌ {username}[/red]: {user_result['error']}")
                else:
                    added = user_result.get("added", 0)
                    skipped = user_result.get("skipped", 0)
                    console.print(
                        f"  [green]✅ {username}[/green]: {added} added, {skipped} skipped"
                    )

    try:
        asyncio.run(run_batch_sync())
    except KeyboardInterrupt:
        display_warning("Batch operation cancelled by user")
        raise typer.Exit(130)
    except Exception as e:
        display_error("Batch sync operation failed", e)
        raise typer.Exit(1)


# --- Utility Commands ---


@app.command("init")
def init_command(
    ctx: typer.Context,
    output_path: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output path for config file (default: .env in current directory)",
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing config file if it exists"
    ),
):
    """
    Initialize a new configuration file with platform-specific defaults.

    Creates a .env file with sensible defaults for your operating system,
    including common service URLs and configuration options.

    [bold]Examples:[/bold]
        seadexarr init
        seadexarr init --output=config/production.env
        seadexarr init --force  # Overwrite existing file
    """
    # Determine output path
    if output_path is None:
        output_path = Path.cwd() / ".env"

    # Check if file exists and handle force flag
    if output_path.exists() and not force:
        display_error(f"Configuration file already exists: {output_path}")
        console.print(
            "[dim]Use --force to overwrite or specify a different --output path[/dim]"
        )
        raise typer.Exit(1)

    # Detect platform
    system = platform.system().lower()
    is_windows = system == "windows"
    is_docker = Path("/.dockerenv").exists()

    # Generate platform-specific configuration
    config_content = generate_platform_config(is_windows, is_docker)

    try:
        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write configuration file
        with output_path.open("w", encoding="utf-8") as f:
            f.write(config_content)

        display_success(f"Configuration file created: {output_path}")

        # Show next steps
        console.print("\n[bold]Next Steps:[/bold]")
        console.print(
            "1. [cyan]Edit the configuration file and add your API keys and URLs[/cyan]"
        )
        console.print(
            "2. [cyan]Run 'seadexarr config-validate' to verify your settings[/cyan]"
        )
        console.print(
            "3. [cyan]Use 'seadexarr status' to test service connectivity[/cyan]"
        )

        # Platform-specific hints
        if is_windows:
            console.print("\n[dim]💡 Windows Tips:[/dim]")
            console.print(
                "[dim]• Use forward slashes (/) in paths, even on Windows[/dim]"
            )
            console.print("[dim]• Default service URLs assume local installation[/dim]")
        else:
            console.print("\n[dim]💡 Linux/macOS Tips:[/dim]")
            console.print("[dim]• Check service URLs if using Docker containers[/dim]")
            console.print("[dim]• Verify file permissions for config directory[/dim]")

        if is_docker:
            console.print(
                "\n[dim]🐳 Docker detected - using container-appropriate defaults[/dim]"
            )

    except Exception as e:
        display_error(f"Failed to create configuration file: {e}")
        raise typer.Exit(1)


def generate_platform_config(is_windows: bool, is_docker: bool) -> str:
    """Generate platform-specific configuration content."""

    # Base configuration template
    config_lines = [
        "# SeaDexArr Configuration File",
        f"# Generated for: {'Windows' if is_windows else 'Linux/macOS'}"
        + (" (Docker)" if is_docker else ""),
        "# Edit the values below with your actual API keys and service URLs",
        "",
        "# =============================================================================",
        "# REQUIRED SETTINGS - These must be configured for SeaDexArr to work",
        "# =============================================================================",
        "",
        "# AniList API Access Token",
        "# Get this from: https://anilist.co/settings/developer",
        "SEADEXARR_ANILIST_ACCESS_TOKEN=your_anilist_access_token_here",
        "",
        "# SeaDx API Configuration",
        "# Contact SeaDx for API access",
        "SEADEXARR_SEADX_API_KEY=your_seadx_api_key_here",
        "SEADEXARR_SEADX_BASE_URL=https://seadx.example.com/api/v1",
        "",
        "# =============================================================================",
        "# SONARR CONFIGURATION - For anime series sync",
        "# =============================================================================",
        "",
    ]

    # Platform-specific Sonarr defaults
    if is_docker:
        config_lines.extend(
            [
                "# Sonarr URL (Docker container name or service)",
                "SEADEXARR_SONARR_URL=http://sonarr:8989",
            ]
        )
    elif is_windows:
        config_lines.extend(
            [
                "# Sonarr URL (Windows default)",
                "SEADEXARR_SONARR_URL=http://localhost:8989",
            ]
        )
    else:
        config_lines.extend(
            [
                "# Sonarr URL (Linux/macOS default)",
                "SEADEXARR_SONARR_URL=http://localhost:8989",
            ]
        )

    config_lines.extend(
        [
            "# Sonarr API Key (found in Sonarr Settings > General)",
            "SEADEXARR_SONARR_API_KEY=your_sonarr_api_key_here",
            "",
            "# =============================================================================",
            "# RADARR CONFIGURATION - For anime movies sync",
            "# =============================================================================",
            "",
        ]
    )

    # Platform-specific Radarr defaults
    if is_docker:
        config_lines.extend(
            [
                "# Radarr URL (Docker container name or service)",
                "SEADEXARR_RADARR_URL=http://radarr:7878",
            ]
        )
    elif is_windows:
        config_lines.extend(
            [
                "# Radarr URL (Windows default)",
                "SEADEXARR_RADARR_URL=http://localhost:7878",
            ]
        )
    else:
        config_lines.extend(
            [
                "# Radarr URL (Linux/macOS default)",
                "SEADEXARR_RADARR_URL=http://localhost:7878",
            ]
        )

    config_lines.extend(
        [
            "# Radarr API Key (found in Radarr Settings > General)",
            "SEADEXARR_RADARR_API_KEY=your_radarr_api_key_here",
            "",
            "# =============================================================================",
            "# OPTIONAL TORRENT CLIENT CONFIGURATION",
            "# =============================================================================",
            "",
        ]
    )

    # Platform-specific qBittorrent defaults
    if is_docker:
        config_lines.extend(
            [
                "# qBittorrent Configuration (Docker)",
                "# SEADEXARR_QBITTORRENT_HOST=http://qbittorrent:8080",
            ]
        )
    elif is_windows:
        config_lines.extend(
            [
                "# qBittorrent Configuration (Windows)",
                "# SEADEXARR_QBITTORRENT_HOST=http://localhost:8080",
            ]
        )
    else:
        config_lines.extend(
            [
                "# qBittorrent Configuration (Linux/macOS)",
                "# SEADEXARR_QBITTORRENT_HOST=http://localhost:8080",
            ]
        )

    config_lines.extend(
        [
            "# SEADEXARR_QBITTORRENT_USERNAME=admin",
            "# SEADEXARR_QBITTORRENT_PASSWORD=your_password",
            "",
            "# =============================================================================",
            "# ADVANCED SETTINGS - Usually don't need to change these",
            "# =============================================================================",
            "",
            "# Logging Configuration",
            "SEADEXARR_LOG_LEVEL=INFO",
            "SEADEXARR_LOG_FORMAT=console",
            "# SEADEXARR_LOG_FILE=seadexarr.log",
            "",
            "# HTTP Client Settings",
            "SEADEXARR_HTTP_TIMEOUT=30.0",
            "SEADEXARR_HTTP_RETRIES=3",
            "",
            "# Default Behavior",
            "SEADEXARR_DRY_RUN=false",
            "",
            "# =============================================================================",
            "# DOCKER-SPECIFIC SETTINGS (only needed in Docker environments)",
            "# =============================================================================",
            "",
        ]
    )

    if is_docker:
        config_lines.extend(
            [
                "# Docker environment flag",
                "DOCKER_ENV=true",
                "CONFIG_DIR=/config",
            ]
        )
    else:
        config_lines.extend(
            [
                "# Uncomment if running in Docker",
                "# DOCKER_ENV=true",
                "# CONFIG_DIR=/config",
            ]
        )

    config_lines.extend(
        [
            "",
            "# =============================================================================",
            "# USAGE EXAMPLES",
            "# =============================================================================",
            "#",
            "# Sync single user to Sonarr:",
            "#   seadexarr sync sonarr your_anilist_username",
            "#",
            "# Batch sync multiple users:",
            "#   seadexarr sync-batch user1 user2 user3 --target=sonarr",
            "#",
            "# Test configuration:",
            "#   seadexarr config-validate",
            "#",
            "# Check service status:",
            "#   seadexarr status",
            "#",
            "# Search for releases:",
            '#   seadexarr search-releases "Attack on Titan"',
            "",
        ]
    )

    return "\n".join(config_lines)


@app.command("search-releases")
def search_releases_command(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(10, "--limit", "-l", help="Maximum number of results"),
    quality_filter: list[str] | None = typer.Option(
        None, "--quality", "-q", help="Quality filters to apply"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview results without downloading"
    ),
):
    """
    Search for releases on SeaDx.

    Examples:
        seadexarr search "Attack on Titan"
        seadexarr search "Your Name" --quality "1080p" --limit 5
    """
    settings = ctx.obj["settings"]

    async def run_search():
        operation_name = f"Searching for '{query}'"

        result = await run_with_progress(
            operation_name,
            sync.find_and_download_releases,
            query,
            settings,
            quality_filter,
            dry_run,
        )

        if "error" in result:
            display_error(result["error"])
            return

        # Display search statistics
        stats_text = f"Found {result['found']} releases"
        if quality_filter:
            stats_text += f", filtered to {result['filtered']} releases"

        console.print(f"[green]✓[/green] {stats_text}")

        # Display results table
        if result["releases"]:
            table = Table(title=f"Search Results for '{query}'", show_lines=True)
            table.add_column("Name", style="white", max_width=60)
            table.add_column("Size", justify="right", style="cyan", min_width=10)
            table.add_column("Quality", style="green", min_width=8)
            table.add_column("Group", style="yellow", min_width=12)

            for release in result["releases"][:limit]:
                size_gb = release["size"] / (1024**3) if release["size"] else 0
                size_str = f"{size_gb:.1f} GB" if size_gb else "Unknown"

                # Truncate long names
                name = release["name"]
                if len(name) > 60:
                    name = name[:57] + "..."

                table.add_row(
                    name,
                    size_str,
                    release["quality"] or "Unknown",
                    release["group"] or "Unknown",
                )

            console.print(table)

            if len(result["releases"]) > limit:
                console.print(
                    f"[dim]... and {len(result['releases']) - limit} more results[/dim]"
                )
        else:
            display_warning("No releases found matching criteria")

    try:
        asyncio.run(run_search())
    except KeyboardInterrupt:
        display_warning("Search cancelled by user")
        raise typer.Exit(130)
    except Exception as e:
        display_error("Search operation failed", e)
        raise typer.Exit(1)


@app.command("status")
def status_command(
    ctx: typer.Context,
    config: Path | None = typer.Option(
        None, "--config", help="Specific config file to check"
    ),
):
    """
    Check the status and connectivity of all configured services.

    Tests connections to AniList, SeaDx, Sonarr, and Radarr to verify
    that all services are properly configured and accessible.

    [bold]Examples:[/bold]
        seadexarr status
        seadexarr status --config=production.env
    """
    settings = get_configured_settings(config) if config else ctx.obj["settings"]

    async def check_status():
        operation_name = "Checking service connectivity"

        result = await run_with_progress(
            operation_name, sync.check_sync_status, settings
        )

        # Create status table
        table = Table(title="Service Status", show_header=True)
        table.add_column("Service", style="cyan", min_width=10)
        table.add_column("Configured", justify="center", style="white", min_width=12)
        table.add_column("Accessible", justify="center", style="white", min_width=12)
        table.add_column("Status", style="white", min_width=15)

        for service_name, status in result.items():
            configured = "✅ Yes" if status["configured"] else "❌ No"

            if status["configured"]:
                accessible = "✅ Yes" if status["accessible"] else "❌ No"
                overall_status = (
                    "🟢 Ready" if status["accessible"] else "🔴 Unreachable"
                )
            else:
                accessible = "- N/A"
                overall_status = "⚙️ Not Configured"

            table.add_row(service_name.title(), configured, accessible, overall_status)

        console.print(table)

        # Show configuration hints
        missing_configs = [
            name for name, status in result.items() if not status["configured"]
        ]
        if missing_configs:
            console.print("\n[yellow]⚠ Missing configuration:[/yellow]")
            for service in missing_configs:
                console.print(f"  • {service.title()}")

            console.print(
                "\n[dim]Set environment variables or use a .env file to configure services.[/dim]"
            )
            console.print(
                "[dim]Run 'seadexarr config-validate' for detailed configuration help.[/dim]"
            )
        else:
            display_success("All services are properly configured!")

    try:
        asyncio.run(check_status())
    except Exception as e:
        display_error("Status check failed", e)
        raise typer.Exit(1)


@app.command("config-validate")
def config_validate_command(
    config_path: Path | None = typer.Argument(
        None, help="Configuration file to validate (defaults to current config)"
    )
):
    """
    Validate configuration settings and show detailed status.

    Checks all configuration options, shows current values (without exposing
    sensitive data), and provides helpful hints for missing configurations.

    [bold]Examples:[/bold]
        seadexarr config-validate
        seadexarr config-validate /path/to/config.env
    """
    try:
        settings = get_configured_settings(config_path)
    except Exception as e:
        display_error("Failed to load configuration", e)
        raise typer.Exit(1)

    # Configuration validation table
    table = Table(title="Configuration Validation", show_header=True)
    table.add_column("Setting", style="cyan", min_width=20)
    table.add_column("Value", style="white", min_width=25)
    table.add_column("Status", style="green", min_width=12)
    table.add_column("Notes", style="dim", min_width=20)

    # Define configuration items with validation
    config_items = [
        # Logging
        ("Log Level", settings.log_level, "✅", ""),
        ("Log Format", settings.log_format, "✅", ""),
        # Core Services
        (
            "AniList Token",
            "Configured" if settings.anilist_access_token else "Not Set",
            "✅" if settings.anilist_access_token else "❌",
            "Required for syncing",
        ),
        (
            "SeaDx API Key",
            "Configured" if settings.seadx_api_key else "Not Set",
            "✅" if settings.seadx_api_key else "❌",
            "Required for searching",
        ),
        ("SeaDx URL", settings.seadx_base_url, "✅", ""),
        # Sonarr
        (
            "Sonarr URL",
            settings.sonarr_url or "Not Set",
            "✅" if settings.sonarr_url else "❌",
            "Required for TV sync",
        ),
        (
            "Sonarr API Key",
            "Configured" if settings.sonarr_api_key else "Not Set",
            "✅" if settings.sonarr_api_key else "❌",
            "Required for TV sync",
        ),
        # Radarr
        (
            "Radarr URL",
            settings.radarr_url or "Not Set",
            "✅" if settings.radarr_url else "❌",
            "Required for movie sync",
        ),
        (
            "Radarr API Key",
            "Configured" if settings.radarr_api_key else "Not Set",
            "✅" if settings.radarr_api_key else "❌",
            "Required for movie sync",
        ),
        # Optional Services
        (
            "qBittorrent Host",
            settings.qbittorrent_host or "Not Set",
            "⚠️" if not settings.qbittorrent_host else "✅",
            "Optional for downloads",
        ),
        # Performance Settings
        ("HTTP Timeout", f"{settings.http_timeout}s", "✅", ""),
        ("HTTP Retries", str(settings.http_retries), "✅", ""),
        ("Dry Run Mode", "Yes" if settings.dry_run else "No", "✅", "Default behavior"),
    ]

    warnings_count = 0
    errors_count = 0

    for setting, value, status, notes in config_items:
        table.add_row(setting, value, status, notes)
        if status == "❌":
            errors_count += 1
        elif status == "⚠️":
            warnings_count += 1

    console.print(table)

    # Summary
    console.print("\n[bold]Configuration Summary:[/bold]")
    if errors_count == 0 and warnings_count == 0:
        display_success("Configuration is complete and valid!")
    else:
        if errors_count > 0:
            console.print(
                f"[red]❌ {errors_count} critical configuration(s) missing[/red]"
            )
        if warnings_count > 0:
            console.print(
                f"[yellow]⚠️ {warnings_count} optional configuration(s) missing[/yellow]"
            )

    # Environment variable hints
    if errors_count > 0:
        console.print("\n[bold]Environment Variables:[/bold]")
        env_hints = [
            "SEADEXARR_ANILIST_ACCESS_TOKEN=your_anilist_token",
            "SEADEXARR_SEADX_API_KEY=your_seadx_api_key",
            "SEADEXARR_SONARR_URL=http://your-sonarr:8989",
            "SEADEXARR_SONARR_API_KEY=your_sonarr_api_key",
            "SEADEXARR_RADARR_URL=http://your-radarr:7878",
            "SEADEXARR_RADARR_API_KEY=your_radarr_api_key",
        ]

        for hint in env_hints:
            console.print(f"  {hint}")


@app.command("config-info")
def config_info_command(ctx: typer.Context):
    """
    Show current configuration in a readable format.

    [dim]Alias for config-validate with current settings.[/dim]
    """
    config_validate_command()


# --- Legacy Support Functions ---


async def legacy_sync_sonarr(
    username: str, settings: Settings, dry_run: bool, verbose: bool
):
    """Legacy support for --sonarr option."""
    result = await sync.sync_anilist_to_sonarr(username, settings, dry_run)
    display_sync_results(
        result, f"Legacy AniList → Sonarr Sync for {username}", verbose
    )


async def legacy_sync_radarr(
    username: str, settings: Settings, dry_run: bool, verbose: bool
):
    """Legacy support for --radarr option."""
    result = await sync.anilist_to_radarr(username, settings, dry_run)
    display_sync_results(
        result, f"Legacy AniList → Radarr Sync for {username}", verbose
    )


# --- Error Handling ---


def handle_keyboard_interrupt():
    """Handle Ctrl+C gracefully."""
    display_warning("Operation cancelled by user")
    raise typer.Exit(130)


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        handle_keyboard_interrupt()
