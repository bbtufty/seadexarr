import copy
import os
import shutil
import time
import traceback
from datetime import datetime, timedelta

import typer

from .seadex_arr import setup_logger
from .seadex_radarr import SeaDexRadarr
from .seadex_sonarr import SeaDexSonarr

seadexarr_cli = typer.Typer(name="seadexarr_cli")
seadexarr_run = typer.Typer(name="run")
seadexarr_config = typer.Typer(name="config")
seadexarr_cache = typer.Typer(name="cache")

seadexarr_cli.add_typer(seadexarr_run)
seadexarr_cli.add_typer(seadexarr_config)
seadexarr_cli.add_typer(seadexarr_cache)


# Default command, schedule run
@seadexarr_cli.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """Run SeaDexArr in scheduled mode

    Will run both Radarr and Sonarr modules
    """

    # Only run this if there's nothing going on
    if ctx.invoked_subcommand is None:
        run_scheduled()

    return True


@seadexarr_run.command("scheduled")
def run_scheduled():
    """Run SeaDexArr in scheduled mode

    Will run both Radarr and Sonarr modules
    """

    # Set up config file location
    config_dir = os.getenv("CONFIG_DIR", os.getcwd())
    config = os.path.join(config_dir, "config.yml")
    cache = os.path.join(config_dir, "cache.json")

    # Get how often to run things
    schedule_time = float(os.getenv("SCHEDULE_TIME", 6))

    while True:

        logger = setup_logger(log_level="INFO")
        logger.info(f"Running in scheduled mode")

        present_time = datetime.now().strftime("%H:%M")
        logger.info(f"Time is {present_time}. Starting scheduled run")

        # Run both Radarr and Sonarr syncs, catching
        # errors if they do arise. Split them up
        # so one crashing doesn't ruin the other
        try:
            sdr = SeaDexRadarr(
                config=config,
                cache=cache,
                logger=logger,
            )
            sdr.run()
        except Exception:
            tb = traceback.format_exc()
            for line in tb.splitlines():
                logger.warning(line)

        try:
            sds = SeaDexSonarr(
                config=config,
                cache=cache,
                logger=logger,
            )
            sds.run()
        except Exception:
            tb = traceback.format_exc()
            for line in tb.splitlines():
                logger.warning(line)

        next_run_time = datetime.now() + timedelta(hours=schedule_time)
        next_run_time = next_run_time.strftime("%H:%M")
        logger.info(f"Scheduled run complete! Will run again at {next_run_time}")

        # Good job, have a rest
        time.sleep(schedule_time * 3600)


# Single run
@seadexarr_run.command("single")
def run_single(
    radarr: bool = False,
    sonarr: bool = False,
):
    """Do a single SeaDexArr run

    Args:
        sonarr: Do a Sonarr run? Defaults to False
        radarr: Do a Radarr run? Defaults to False
    """

    # Set up config file location
    config_dir = os.getenv("CONFIG_DIR", os.getcwd())
    config = os.path.join(config_dir, "config.yml")
    cache = os.path.join(config_dir, "cache.json")

    logger = setup_logger(log_level="INFO")

    if radarr:
        try:
            sdr = SeaDexRadarr(
                config=config,
                cache=cache,
                logger=logger,
            )
            sdr.run()
        except Exception:
            tb = traceback.format_exc()
            for line in tb.splitlines():
                logger.warning(line)

    if sonarr:
        try:
            sds = SeaDexSonarr(
                config=config,
                cache=cache,
                logger=logger,
            )
            sds.run()
        except Exception:
            tb = traceback.format_exc()
            for line in tb.splitlines():
                logger.warning(line)

    return True


# Config commands
@seadexarr_config.command("init")
def config_init():
    """Initialise a configuration file.

    If not running in Docker, will create a config.yml in the current working
    directory. For Docker, will create config.yml in the /config directory
    """

    f_path = copy.deepcopy(__file__)
    config_template_path = os.path.join(os.path.dirname(f_path), "config_sample.yml")

    config_dir = os.environ.get("CONFIG_DIR", os.getcwd())
    config = os.path.join(config_dir, "config.yml")

    shutil.copyfile(config_template_path, config)

    return True


# Cache commands
@seadexarr_cache.command("backup")
def cache_backup():
    """Backup cache file.

    Will rename cache to cache.backup.json
    """

    config_dir = os.environ.get("CONFIG_DIR", os.getcwd())
    cache = os.path.join(config_dir, "cache.json")
    backup_cache = os.path.join(config_dir, "cache.backup.json")

    shutil.copyfile(cache, backup_cache)

    return True


@seadexarr_cache.command("restore")
def cache_restore():
    """Restore cache file.

    Will rename cache.backup.json to cache.json
    """

    config_dir = os.environ.get("CONFIG_DIR", os.getcwd())
    cache = os.path.join(config_dir, "cache.json")
    backup_cache = os.path.join(config_dir, "cache.backup.json")

    if os.path.exists(backup_cache):
        shutil.move(backup_cache, cache)
    else:
        raise FileNotFoundError(f"File {backup_cache} not found")

    return True


@seadexarr_cache.command("remove")
def cache_remove():
    """Remove cache file.

    Will remove cache.json
    """

    config_dir = os.environ.get("CONFIG_DIR", os.getcwd())
    cache = os.path.join(config_dir, "cache.json")

    if os.path.exists(cache):
        os.remove(cache)
    else:
        raise FileNotFoundError(f"File {cache} not found")

    return True
