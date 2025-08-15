"""
Modern CLI interface for SeaDexArr using Typer.

Production-ready command-line interface with comprehensive async support,
Rich formatting, enhanced error handling, and proper exit codes.
"""

import asyncio
import platform
import signal
import sys
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
from rich.traceback import install as install_rich_traceback

from ..config import Settings, get_settings
from ..core import sync
from ..utils.exceptions import (
    APIError,
    ConfigurationError,
    ErrorCategory,
    ErrorSeverity,
    NetworkError,
    SeaDexArrError,
    ValidationError,
)
from ..utils.logging import (
    generate_correlation_id,
    get_logger,
    operation_logger,
    setup_enhanced_logging,
)

# Install rich traceback for better error display
install_rich_traceback(show_locals=False)

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

# Global settings and logger
_settings: Settings | None = None
_logger = get_logger(__name__)


# Exit codes for different error scenarios
class ExitCodes:
    SUCCESS = 0
    GENERAL_ERROR = 1
    CONFIGURATION_ERROR = 2
    NETWORK_ERROR = 3
    API_ERROR = 4
    VALIDATION_ERROR = 5
    AUTHENTICATION_ERROR = 6
    AUTHORIZATION_ERROR = 7
    SERVICE_UNAVAILABLE = 8
    TIMEOUT_ERROR = 9
    USER_INTERRUPTED = 130  # Standard SIGINT exit code


def get_exit_code_for_error(error: Exception) -> int:
    """Determine appropriate exit code based on error type."""
    if isinstance(error, SeaDexArrError):
        category_to_exit_code = {
            ErrorCategory.CONFIGURATION_ERROR: ExitCodes.CONFIGURATION_ERROR,
            ErrorCategory.NETWORK_ERROR: ExitCodes.NETWORK_ERROR,
            ErrorCategory.API_ERROR: ExitCodes.API_ERROR,
            ErrorCategory.USER_ERROR: ExitCodes.VALIDATION_ERROR,
            ErrorCategory.SECURITY_ERROR: ExitCodes.AUTHENTICATION_ERROR,
            ErrorCategory.EXTERNAL_SERVICE_ERROR: ExitCodes.SERVICE_UNAVAILABLE,
            ErrorCategory.PERFORMANCE_ERROR: ExitCodes.TIMEOUT_ERROR,
        }
        return category_to_exit_code.get(error.category, ExitCodes.GENERAL_ERROR)
    
    # Handle specific exception types
    if isinstance(error, ConfigurationError | ValidationError):
        return ExitCodes.CONFIGURATION_ERROR
    elif isinstance(error, NetworkError):
        return ExitCodes.NETWORK_ERROR
    elif isinstance(error, APIError):
        return ExitCodes.API_ERROR
    elif isinstance(error, KeyboardInterrupt):
        return ExitCodes.USER_INTERRUPTED
    
    return ExitCodes.GENERAL_ERROR


def setup_signal_handlers():
    """Setup graceful signal handling for user interruptions."""

    def signal_handler(signum, frame):
        signal_name = signal.Signals(signum).name
        _logger.info(f"Received {signal_name}, shutting down gracefully...")

        console.print(
            f"\n[yellow]⚠️  Received {signal_name}, shutting down gracefully...[/yellow]"
        )

        # Cancel all running tasks
        try:
            loop = asyncio.get_running_loop()
            tasks = [task for task in asyncio.all_tasks(loop) if not task.done()]
            for task in tasks:
                task.cancel()
        except RuntimeError:
            pass  # No running loop

        sys.exit(ExitCodes.USER_INTERRUPTED)

    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, signal_handler)


def get_configured_settings(config_path: Path | None = None) -> Settings:
    """Get configured settings with enhanced error handling."""
    global _settings

    try:
        if _settings is None or config_path is not None:
            if config_path and config_path.exists():
                _settings = Settings(_env_file=str(config_path))
                _logger.info(f"Loaded configuration from {config_path}")
            else:
                _settings = get_settings()
                _logger.debug("Using default configuration")
    except Exception as e:
        raise ConfigurationError(
            f"Failed to load configuration: {e!s}",
            config_key="configuration_file" if config_path else "default_settings",
            actual_value=str(config_path) if config_path else "default",
            correlation_id=generate_correlation_id(),
        )

    return _settings


def setup_logging_for_cli(
    verbose: bool = False,
    quiet: bool = False,
    format_type: str = "console",
    correlation_id: str | None = None,
) -> None:
    """Setup enhanced logging for CLI operations."""
    try:
        json_logs = format_type == "json"

        # Use enhanced logging setup
        setup_enhanced_logging(
            verbose=verbose,
            quiet=quiet,
            json_logs=json_logs,
            enable_performance_logging=True,
            enable_security_logging=True,
            sample_rate=1.0 if verbose else 0.8,  # Reduce sampling in non-verbose mode
        )

        if correlation_id:
            _logger.with_correlation_id(correlation_id)

        _logger.debug(
            "CLI logging configured",
            verbose=verbose,
            quiet=quiet,
            format_type=format_type,
            correlation_id=correlation_id,
        )

    except Exception as e:
        # Fallback to basic logging if enhanced setup fails
        import logging

        logging.basicConfig(
            level=logging.DEBUG if verbose else logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        console.print(
            f"[yellow]Warning: Enhanced logging setup failed, using basic logging: {e}[/yellow]"
        )


def display_enhanced_error(
    message: str,
    exception: Exception | None = None,
    show_hints: bool = True,
    show_correlation_id: bool = False,
) -> None:
    """Display enhanced error message with rich formatting and troubleshooting hints."""
    console.print(f"[red]✗ Error:[/red] {message}")

    if isinstance(exception, SeaDexArrError):
        # Show user-friendly message if different from technical message
        if exception.user_message != exception.message:
            console.print(f"[dim red]Details: {exception.user_message}[/dim red]")

        # Show error category and severity
        console.print(
            f"[dim]Category: {exception.category.value.replace('_', ' ').title()}[/dim]"
        )
        if exception.severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
            console.print(
                f"[dim red]Severity: {exception.severity.value.upper()}[/dim red]"
            )

        # Show correlation ID for debugging
        if show_correlation_id and exception.correlation_id:
            console.print(f"[dim]Correlation ID: {exception.correlation_id}[/dim]")

        # Show troubleshooting hints
        if show_hints and exception.troubleshooting_hints:
            console.print("\n[bold yellow]💡 Troubleshooting Tips:[/bold yellow]")
            for i, hint in enumerate(exception.troubleshooting_hints, 1):
                console.print(f"  {i}. {hint}")

        # Show retryability
        if exception.retryable:
            console.print("[dim green]i  This error is retryable[/dim green]")

    elif exception:
        console.print(f"[dim red]Details: {exception}[/dim red]")

        # Show general troubleshooting for non-SeaDexArr errors
        if show_hints:
            console.print("\n[bold yellow]💡 General Troubleshooting:[/bold yellow]")
            console.print("  1. Check the application logs for more details")
            console.print(
                "  2. Verify your configuration with 'seadexarr config-validate'"
            )
            console.print("  3. Check service connectivity with 'seadexarr status'")

    # Log the error for debugging
    _logger.error(
        f"CLI Error: {message}", error=exception, message=message, show_hints=show_hints
    )


def display_success(message: str, details: dict[str, Any] | None = None) -> None:
    """Display success message with optional details."""
    console.print(f"[green]✓[/green] {message}")

    if details:
        _logger.info("Operation completed successfully", **details)


def display_warning(message: str, details: dict[str, Any] | None = None) -> None:
    """Display warning message with optional details."""
    console.print(f"[yellow]⚠[/yellow] {message}")

    if details:
        _logger.warning("CLI Warning", warning=message, **details)


def display_info(message: str, details: dict[str, Any] | None = None) -> None:
    """Display info message with optional details."""
    console.print(f"[blue]i[/blue] {message}")
    
    if details:
        _logger.info("CLI Info", info=message, **details)


def display_sync_results(
    results: dict[str, Any], 
    title: str, 
    verbose: bool = False,
    correlation_id: str | None = None
) -> None:
    """Display sync results with enhanced formatting and logging."""
    # Log the results for observability
    _logger.performance(
        f"Sync operation completed: {title}",
        duration_ms=0,  # Duration would be calculated by the operation logger
        results=results,
        correlation_id=correlation_id
    )
    
    if "error" in results:
        display_enhanced_error(
            results["error"], 
            show_hints=True,
            show_correlation_id=bool(correlation_id)
        )
        return

    # Main results table with enhanced styling
    table = Table(
        title=f"[bold magenta]{title}[/bold magenta]", 
        show_header=True, 
        header_style="bold magenta",
        border_style="blue"
    )
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
        # Color-code the count based on metric type
        if metric == "Errors" and count > 0:
            count_style = "red"
        elif metric == "Added" and count > 0:
            count_style = "green"
        elif metric == "Skipped" and count > 0:
            count_style = "yellow"
        else:
            count_style = "white"
        
        table.add_row(metric, f"[{count_style}]{count}[/{count_style}]", status)

    console.print(table)

    # Show performance summary
    total_operations = results.get("processed", 0)
    if total_operations > 0:
        success_rate = ((total_operations - results.get("errors", 0)) / total_operations) * 100
        console.print(f"[dim]Success Rate: {success_rate:.1f}%[/dim]")

    # Detailed results if verbose
    if verbose and results.get("details"):
        console.print(f"\n[bold]Operation Details ({len(results['details'])} items):[/bold]")

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


async def run_with_progress_and_logging(
    operation_name: str,
    operation_func,
    *args,
    show_spinner: bool = True,
    correlation_id: str | None = None,
    **kwargs,
) -> Any:
    """Run an async operation with progress indicator and enhanced logging."""
    correlation_id = correlation_id or generate_correlation_id()

    with operation_logger(operation_name, correlation_id) as op_logger:
        try:
            if show_spinner:
                with console.status(f"[bold blue]{operation_name}..."):
                    result = await operation_func(*args, **kwargs)
            else:
                result = await operation_func(*args, **kwargs)

            op_logger.info(f"Operation completed successfully: {operation_name}")
            return result

        except Exception as e:
            op_logger.error(
                f"Operation failed: {operation_name}",
                error=e,
                correlation_id=correlation_id,
            )
            raise


def handle_cli_exception(
    operation: str,
    exception: Exception,
    verbose: bool = False,
    correlation_id: str | None = None,
) -> int:
    """Centralized CLI exception handling with proper exit codes."""
    exit_code = get_exit_code_for_error(exception)

    if isinstance(exception, KeyboardInterrupt):
        display_warning("Operation cancelled by user")
        _logger.info("User interrupted operation", operation=operation)
    else:
        error_message = f"{operation} failed"
        display_enhanced_error(
            error_message,
            exception,
            show_hints=True,
            show_correlation_id=verbose and bool(correlation_id),
        )

    return exit_code


@app.callback()
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose logging and detailed output"
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
    correlation_id: str | None = typer.Option(
        None, "--correlation-id", help="Set correlation ID for request tracking"
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
    # Setup signal handlers for graceful shutdown
    setup_signal_handlers()

    # Generate correlation ID if not provided
    correlation_id = correlation_id or generate_correlation_id()

    # Setup logging first
    try:
        setup_logging_for_cli(verbose, quiet, correlation_id=correlation_id)
    except Exception as e:
        console.print(f"[red]Failed to setup logging: {e}[/red]")
        raise typer.Exit(ExitCodes.CONFIGURATION_ERROR)

    # Load settings with error handling
    try:
        settings = get_configured_settings(config)
    except ConfigurationError as e:
        display_enhanced_error("Configuration error", e, show_hints=True)
        raise typer.Exit(get_exit_code_for_error(e))
    except Exception as e:
        display_enhanced_error("Failed to load configuration", e)
        raise typer.Exit(ExitCodes.CONFIGURATION_ERROR)

    # Store context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["settings"] = settings
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet
    ctx.obj["dry_run"] = dry_run
    ctx.obj["correlation_id"] = correlation_id

    # Handle legacy compatibility with warnings
    if sonarr_user:
        display_warning(
            "Using legacy --sonarr option. Consider using 'seadexarr sync sonarr' instead.",
            details={"user": sonarr_user, "legacy_mode": True},
        )
        try:
            asyncio.run(
                legacy_sync_sonarr(
                    sonarr_user, settings, dry_run, verbose, correlation_id
                )
            )
        except Exception as e:
            exit_code = handle_cli_exception(
                "Legacy Sonarr sync", e, verbose, correlation_id
            )
            raise typer.Exit(exit_code)
        raise typer.Exit(ExitCodes.SUCCESS)

    if radarr_user:
        display_warning(
            "Using legacy --radarr option. Consider using 'seadexarr sync radarr' instead.",
            details={"user": radarr_user, "legacy_mode": True},
        )
        try:
            asyncio.run(
                legacy_sync_radarr(
                    radarr_user, settings, dry_run, verbose, correlation_id
                )
            )
        except Exception as e:
            exit_code = handle_cli_exception(
                "Legacy Radarr sync", e, verbose, correlation_id
            )
            raise typer.Exit(exit_code)
        raise typer.Exit(ExitCodes.SUCCESS)


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
    correlation_id = ctx.obj["correlation_id"]
    is_dry_run = dry_run if dry_run is not None else ctx.obj["dry_run"]

    async def run_sync():
        operation_name = f"Syncing {username}'s AniList to Sonarr"
        if is_dry_run:
            operation_name += " (Dry Run)"

        result = await run_with_progress_and_logging(
            operation_name,
            sync.sync_anilist_to_sonarr,
            username,
            settings,
            is_dry_run,
            correlation_id=correlation_id,
            show_spinner=True,
        )

        display_sync_results(
            result,
            f"AniList → Sonarr Sync Results for {username}",
            verbose,
            correlation_id,
        )

        if not is_dry_run and result.get("added", 0) > 0 and search_missing:
            display_success(
                f"Added {result['added']} series. Triggering search for missing episodes..."
            )

    try:
        asyncio.run(run_sync())
    except Exception as e:
        exit_code = handle_cli_exception("Sonarr sync", e, verbose, correlation_id)
        raise typer.Exit(exit_code)


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
    correlation_id = ctx.obj["correlation_id"]
    is_dry_run = dry_run if dry_run is not None else ctx.obj["dry_run"]

    async def run_sync():
        operation_name = f"Syncing {username}'s AniList movies to Radarr"
        if is_dry_run:
            operation_name += " (Dry Run)"

        result = await run_with_progress_and_logging(
            operation_name,
            sync.sync_anilist_to_radarr,
            username,
            settings,
            is_dry_run,
            correlation_id=correlation_id,
            show_spinner=True,
        )

        display_sync_results(
            result,
            f"AniList → Radarr Sync Results for {username}",
            verbose,
            correlation_id,
        )

    try:
        asyncio.run(run_sync())
    except Exception as e:
        exit_code = handle_cli_exception("Radarr sync", e, verbose, correlation_id)
        raise typer.Exit(exit_code)


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
        display_enhanced_error(
            "Invalid target service",
            ValidationError(
                f"Target must be 'sonarr' or 'radarr', got '{target}'",
                field_name="target",
                field_value=target,
                validation_rule="must be 'sonarr' or 'radarr'",
            ),
        )
        raise typer.Exit(ExitCodes.VALIDATION_ERROR)

    settings = ctx.obj["settings"]
    verbose = ctx.obj["verbose"]
    correlation_id = ctx.obj["correlation_id"]
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

        # Display enhanced batch results
        table = Table(
            title=f"[bold magenta]Batch Sync Results ({target.title()})[/bold magenta]",
            show_header=True,
            border_style="blue",
        )
        table.add_column("Metric", style="cyan")
        table.add_column("Count", justify="right", style="green")
        table.add_column("Status", style="white")

        table.add_row("Total Users", str(result["total_users"]), "📊")
        table.add_row(
            "Successful",
            f"[green]{result['successful_syncs']}[/green]",
            "✅" if result["successful_syncs"] > 0 else "-",
        )
        table.add_row(
            "Failed",
            f"[red]{result['failed_syncs']}[/red]",
            "❌" if result["failed_syncs"] > 0 else "✅",
        )

        console.print(table)

        # Show success rate
        if result["total_users"] > 0:
            success_rate = (result["successful_syncs"] / result["total_users"]) * 100
            console.print(f"[dim]Success Rate: {success_rate:.1f}%[/dim]")

        # Show per-user results if verbose
        if verbose:
            console.print(
                f"\n[bold]Individual User Results ({len(result['user_results'])} users):[/bold]"
            )
            for username, user_result in result["user_results"].items():
                if "error" in user_result:
                    console.print(f"  [red]❌ {username}[/red]: {user_result['error']}")
                else:
                    added = user_result.get("added", 0)
                    skipped = user_result.get("skipped", 0)
                    console.print(
                        f"  [green]✅ {username}[/green]: {added} added, {skipped} skipped"
                    )

        # Log batch results
        _logger.performance(
            f"Batch sync completed for {target}",
            duration_ms=0,  # Would be calculated by operation logger
            total_users=result["total_users"],
            successful_syncs=result["successful_syncs"],
            failed_syncs=result["failed_syncs"],
            success_rate=success_rate if result["total_users"] > 0 else 0,
            correlation_id=correlation_id,
        )

    try:
        asyncio.run(run_batch_sync())
    except Exception as e:
        exit_code = handle_cli_exception("Batch sync", e, verbose, correlation_id)
        raise typer.Exit(exit_code)


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
    correlation_id = ctx.obj.get("correlation_id")
    verbose = ctx.obj.get("verbose", False)

    try:
        # Determine output path
        if output_path is None:
            output_path = Path.cwd() / ".env"

        # Check if file exists and handle force flag
        if output_path.exists() and not force:
            raise ValidationError(
                f"Configuration file already exists: {output_path}",
                field_name="output_path",
                field_value=str(output_path),
                troubleshooting_hints=[
                    "Use --force to overwrite the existing file",
                    "Specify a different --output path",
                    "Remove the existing file manually if you're sure",
                ],
            )

        # Detect platform
        system = platform.system().lower()
        is_windows = system == "windows"
        is_docker = Path("/.dockerenv").exists()

        _logger.info(
            "Generating configuration file",
            output_path=str(output_path),
            platform=system,
            is_docker=is_docker,
            correlation_id=correlation_id,
        )

        # Generate platform-specific configuration
        config_content = generate_platform_config(is_windows, is_docker)

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

        _logger.audit(
            "configuration_file_created",
            output_path=str(output_path),
            platform=system,
            is_docker=is_docker,
        )

    except Exception as e:
        exit_code = handle_cli_exception(
            "Configuration initialization", e, verbose, correlation_id
        )
        raise typer.Exit(exit_code)


def generate_platform_config(is_windows: bool, is_docker: bool) -> str:
    """Generate platform-specific configuration content with enhanced structure."""

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
            "# ENHANCED LOGGING AND MONITORING SETTINGS",
            "# =============================================================================",
            "",
            "# Logging Configuration",
            "SEADEXARR_LOG_LEVEL=INFO",
            "SEADEXARR_LOG_FORMAT=console",
            "# SEADEXARR_LOG_FILE=logs/seadexarr.log",
            "",
            "# Performance and Reliability Settings",
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
    Search for releases on SeaDx with enhanced filtering and display.

    [bold]Examples:[/bold]
        seadexarr search-releases "Attack on Titan"
        seadexarr search-releases "Your Name" --quality "1080p" --limit 5
    """
    settings = ctx.obj["settings"]
    verbose = ctx.obj["verbose"]
    correlation_id = ctx.obj["correlation_id"]

    async def run_search():
        operation_name = f"Searching for '{query}'"

        result = await run_with_progress_and_logging(
            operation_name,
            sync.find_and_download_releases,
            query,
            settings,
            quality_filter,
            dry_run,
            correlation_id=correlation_id,
        )

        if "error" in result:
            display_enhanced_error(result["error"], show_hints=True)
            return

        # Display search statistics
        stats_text = f"Found {result['found']} releases"
        if quality_filter:
            stats_text += f", filtered to {result['filtered']} releases"

        display_success(stats_text)

        # Display enhanced results table
        if result["releases"]:
            table = Table(
                title=f"[bold magenta]Search Results for '{query}'[/bold magenta]",
                show_lines=True,
                border_style="blue",
            )
            table.add_column("Name", style="white", max_width=60)
            table.add_column("Size", justify="right", style="cyan", min_width=10)
            table.add_column("Quality", style="green", min_width=8)
            table.add_column("Group", style="yellow", min_width=12)

            shown_results = result["releases"][:limit]
            for release in shown_results:
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

        # Log search results for analytics
        _logger.audit(
            "search_releases",
            query=query,
            found_count=result["found"],
            filtered_count=result.get("filtered", 0),
            quality_filters=quality_filter,
            correlation_id=correlation_id,
        )

    try:
        asyncio.run(run_search())
    except Exception as e:
        exit_code = handle_cli_exception("Release search", e, verbose, correlation_id)
        raise typer.Exit(exit_code)


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
    verbose = ctx.obj.get("verbose", False)
    correlation_id = ctx.obj.get("correlation_id")

    try:
        settings = get_configured_settings(config) if config else ctx.obj["settings"]
    except Exception as e:
        exit_code = handle_cli_exception(
            "Configuration loading", e, verbose, correlation_id
        )
        raise typer.Exit(exit_code)

    async def check_status():
        operation_name = "Checking service connectivity"

        result = await run_with_progress_and_logging(
            operation_name,
            sync.check_sync_status,
            settings,
            correlation_id=correlation_id,
        )

        # Create enhanced status table
        table = Table(
            title="[bold magenta]Service Status[/bold magenta]",
            show_header=True,
            border_style="blue",
        )
        table.add_column("Service", style="cyan", min_width=10)
        table.add_column("Configured", justify="center", style="white", min_width=12)
        table.add_column("Accessible", justify="center", style="white", min_width=12)
        table.add_column("Status", style="white", min_width=15)

        service_stats = {"configured": 0, "accessible": 0, "total": 0}

        for service_name, status in result.items():
            service_stats["total"] += 1

            if status["configured"]:
                service_stats["configured"] += 1
                configured = "✅ Yes"
            else:
                configured = "❌ No"

            if status["configured"]:
                if status["accessible"]:
                    service_stats["accessible"] += 1
                    accessible = "✅ Yes"
                    overall_status = "🟢 Ready"
                else:
                    accessible = "❌ No"
                    overall_status = "🔴 Unreachable"
            else:
                accessible = "- N/A"
                overall_status = "⚙️ Not Configured"

            table.add_row(service_name.title(), configured, accessible, overall_status)

        console.print(table)

        # Show configuration summary
        console.print(
            f"\n[dim]Summary: {service_stats['accessible']}/{service_stats['configured']}/{service_stats['total']} services ready[/dim]"
        )

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

        # Log status check results
        _logger.audit(
            "service_status_check",
            configured_services=service_stats["configured"],
            accessible_services=service_stats["accessible"],
            total_services=service_stats["total"],
            missing_configs=missing_configs,
            correlation_id=correlation_id,
        )

        return (
            service_stats["accessible"]
            == service_stats["configured"]
            == service_stats["total"]
        )

    try:
        all_services_ready = asyncio.run(check_status())
        if not all_services_ready:
            raise typer.Exit(ExitCodes.CONFIGURATION_ERROR)
    except Exception as e:
        exit_code = handle_cli_exception("Status check", e, verbose, correlation_id)
        raise typer.Exit(exit_code)


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
    correlation_id = generate_correlation_id()

    try:
        settings = get_configured_settings(config_path)
    except Exception as e:
        display_enhanced_error("Failed to load configuration", e)
        raise typer.Exit(ExitCodes.CONFIGURATION_ERROR)

    # Enhanced configuration validation table
    table = Table(
        title="[bold magenta]Configuration Validation[/bold magenta]",
        show_header=True,
        border_style="blue",
    )
    table.add_column("Setting", style="cyan", min_width=20)
    table.add_column("Value", style="white", min_width=25)
    table.add_column("Status", style="green", min_width=12)
    table.add_column("Notes", style="dim", min_width=20)

    # Define configuration items with enhanced validation
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
        # Color-code values based on status
        if status == "❌":
            value_display = f"[red]{value}[/red]"
            errors_count += 1
        elif status == "⚠️":
            value_display = f"[yellow]{value}[/yellow]"
            warnings_count += 1
        else:
            value_display = value

        table.add_row(setting, value_display, status, notes)

    console.print(table)

    # Enhanced summary
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

    # Log configuration validation
    _logger.audit(
        "configuration_validation",
        errors_count=errors_count,
        warnings_count=warnings_count,
        total_settings=len(config_items),
        config_file=str(config_path) if config_path else "default",
        correlation_id=correlation_id,
    )

    if errors_count > 0:
        raise typer.Exit(ExitCodes.CONFIGURATION_ERROR)


@app.command("config-info")
def config_info_command(ctx: typer.Context):
    """
    Show current configuration in a readable format.

    [dim]Alias for config-validate with current settings.[/dim]
    """
    config_validate_command()


# --- Legacy Support Functions ---


async def legacy_sync_sonarr(
    username: str, settings: Settings, dry_run: bool, verbose: bool, correlation_id: str
):
    """Legacy support for --sonarr option with enhanced logging."""
    with operation_logger("legacy_sonarr_sync", correlation_id, username=username):
        result = await sync.sync_anilist_to_sonarr(username, settings, dry_run)
        display_sync_results(
            result,
            f"Legacy AniList → Sonarr Sync for {username}",
            verbose,
            correlation_id,
        )


async def legacy_sync_radarr(
    username: str, settings: Settings, dry_run: bool, verbose: bool, correlation_id: str
):
    """Legacy support for --radarr option with enhanced logging."""
    with operation_logger("legacy_radarr_sync", correlation_id, username=username):
        result = await sync.sync_anilist_to_radarr(username, settings, dry_run)
        display_sync_results(
            result,
            f"Legacy AniList → Radarr Sync for {username}",
            verbose,
            correlation_id,
        )


# --- Enhanced Error Handling ---


def handle_keyboard_interrupt():
    """Handle Ctrl+C gracefully with enhanced logging."""
    _logger.info("User interrupted operation via keyboard")
    display_warning("Operation cancelled by user")
    raise typer.Exit(ExitCodes.USER_INTERRUPTED)


# --- Main Entry Point ---


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        handle_keyboard_interrupt()
    except Exception as e:
        # Last resort error handling
        console.print(f"[red]Unexpected error: {e}[/red]")
        import traceback

        if "--verbose" in sys.argv or "-v" in sys.argv:
            console.print(f"[dim red]{traceback.format_exc()}[/dim red]")
        sys.exit(ExitCodes.GENERAL_ERROR)
