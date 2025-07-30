import argparse
import os
import time
import traceback
from datetime import datetime, timedelta

from seadexarr import SeaDexSonarr, SeaDexRadarr, setup_logger

ALLOWED_ARRS = [
    "radarr",
    "sonarr",
]

# Define the parser and parse args
parser = argparse.ArgumentParser(description="SeaDexArr")
parser.add_argument("--arr", action="store", dest="arr")
args = parser.parse_args()

# See if we're doing a one-run, or scheduling
arr = args.arr

running_schedule = False
if arr is None:
    running_schedule = True

# Set up config file location
config_dir = os.getenv("CONFIG_DIR", os.getcwd())
config = os.path.join(config_dir, "config.yml")

logger = setup_logger(log_level="INFO")

if running_schedule:

    # Get how often to run things
    schedule_time = os.getenv("SCHEDULE_TIME", 6)

    logger.info(f"Running in scheduled mode")

    while True:

        present_time = datetime.now().strftime("%H:%M")
        logger.info(f"Time is {present_time}. Starting run")

        # Run both Radarr and Sonarr syncs, catching
        # errors if they do arise. Split them up
        # so one crashing doesn't ruin the other
        try:
            sdr = SeaDexRadarr(config=config)
            sdr.run()
        except Exception:
            tb = traceback.format_exc()
            for line in tb.splitlines():
                logger.warning(line)

        try:
            sds = SeaDexSonarr(config=config)
            sds.run()
        except Exception:
            tb = traceback.format_exc()
            for line in tb.splitlines():
                logger.warning(line)

        next_run_time = datetime.now() + timedelta(hours=schedule_time)
        next_run_time = next_run_time.strftime('%H:%M')
        logger.info(f"Run complete! Will run again at {next_run_time}")

        # Good job, have a rest
        time.sleep(schedule_time * 3600)

# Else we're in a single run mode
else:

    if arr in ALLOWED_ARRS:

        try:
            if arr == "radarr":
                sdr = SeaDexRadarr(config=config)
                sdr.run()

            elif arr == "sonarr":
                sds = SeaDexSonarr(config=config)
                sds.run()
        except Exception:
            tb = traceback.format_exc()
            for line in tb.splitlines():
                logger.warning(line)

    else:
        logger.warning(f"Arr {arr} unknown")
