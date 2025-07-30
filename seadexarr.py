import argparse
import os

from seadexarr import SeaDexSonarr, SeaDexRadarr

# Define the parser and parse args
parser = argparse.ArgumentParser(description="SeaDexArr")
parser.add_argument("--arr", action="store", dest="arr")
args = parser.parse_args()

# Set up config file location
config_dir = os.getenv("CONFIG_DIR")
config = os.path.join(config_dir, "config.yml")

if args.arr == "radarr":
    sdr = SeaDexRadarr(config=config)
    sdr.run()

elif args.arr == "sonarr":
    sds = SeaDexSonarr(config=config)
    sds.run()

else:
    raise Warning(f"Specify which Arr to run via the --arr flag")
