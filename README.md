# SeaDexArr

[![](https://img.shields.io/pypi/v/seadexarr.svg?label=PyPI&style=flat-square)](https://pypi.org/pypi/seadexarr/)
[![](https://img.shields.io/pypi/pyversions/seadexarr.svg?label=Python&color=yellow&style=flat-square)](https://pypi.org/pypi/seadexarr/)
[![Actions](https://img.shields.io/github/actions/workflow/status/bbtufty/seadexarr/build.yaml?branch=main&style=flat-square)](https://github.com/bbtufty/seadexarr/actions)
[![License](https://img.shields.io/badge/license-GNUv3-blue.svg?label=License&style=flat-square)](LICENSE)

![SeaDexArr](example_post.png)

SeaDexArr is designed as a tool to ensure that you have Anime releases on the Arr apps that match with the best 
releases tagged on SeaDex. SeaDexArr supports both Sonarr and Radarr.

For Sonarr, it works by scanning through series tagged as type "Anime", matching these up via the TVDB ID to AniList 
mappings via the Kometa Anime Mappings (https://github.com/Kometa-Team/Anime-IDs), AniDB mappings 
(https://github.com/Anime-Lists/anime-lists), and ultimately finding releases in the SeaDex database.

For Radarr, this works much the same but instead using the TMDB IDs.

SeaDexArr will then do some cuts to select a "best" release, which can be pushed to Discord via a bot, and added
automatically to a torrent client. This should make it significantly more hands-free to keep the best Anime releases 
out there.

## Installation

SeaDexArr is available as a Docker container. Into a docker-compose file:

```
services:

  seadexarr:
    image: ghcr.io/bbtufty/seadexarr:latest
    container_name: seadexarr
    environment: 
      - SCHEDULE_TIME=6  # How often to run, in hours
    volumes:
      - /path/to/config:/config
    restart: unless-stopped
```

And then to run on a schedule, simply run `docker-compose up -d seadexarr`. If you want to run one Arr one time, you 
can instead run like `docker-compose run seadexarr --arr radarr` (swap out radarr for sonarr depending on which you
want to run).

SeaDexArr can also be installed via pip:

```
pip install seadexarr
```

Or the cutting edge via GitHub:

```
git clone https://github.com/bbtufty/seadexarr.git
cd seadexarr
pip install -e .
```

## Usage

To run SeaDexArr, the Python code is simple:

```
from seadexarr import SeaDexSonarr, SeaDexRadarr

sds = SeaDexSonarr()
sds.run()

sdr = SeaDexRadarr()
sdr.run()
```

On the first run, the code will generate a config file in your working directory. This should be populated to your own 
preference, and then run the code again.

## Config

There are a number of configuration settings to play around with. These should be self-explanatory, but a more detailed
description of each is given below.

### Arr settings

- `sonarr_url`: URL for Sonarr. Required if running SeaDexSonarr
- `sonarr_api_key`: API key for Sonarr (Settings/General/API Key). Required if running SeaDexSonarr

- `radarr_url`: URL for Radarr. Required if running SeaDexRadarr
- `radarr_api_key`: API key for Radarr (Settings/General/API Key). Required if running SeaDexRadarr

### Torrent settings

- `qbit_info`: Details for qBittorrent. This requires a host URL, username, and password to be set. 
   Required if using qBittorrent
- `sonarr_torrent_category`: Sonarr torrent import category, if you have one. Defaults to None, which won't 
   set a category
- `radarr_torrent_category`: Radarr torrent import category, if you have one. Defaults to None, which won't 
   set a category
- `max_torrents_to_add`: used to limit the number of torrents you add in one run. Defaults to None, which 
   will just add everything it finds

### Discord settings

- `discord_url`: If you want to use Discord notifications (recommended), then set up a webhook following 
   [this guide](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks) and add the URL
   here. Defaults to None, which won't use the Discord integration

### SeaDex filters

- `public_only`: Will only return results from public trackers. Defaults to True
- `prefer_dual_audio`: Prefer results tagged as dual audio, if any exist. Defaults to True
- `want_best`: Prefer results tagged as best, if any exist. Defaults to True

### Advanced settings

- `sleep_time`: To avoid hitting API rate limits, after each query SeaDexArr will wait a number 
   of seconds. Defaults to 2
- `cache_time`: The mappings files don't change all the time, so are cached for a certain number
   of days. Defaults to 1
- `interactive`: If True, will enable interactive mode, which when multiple torrent options are
   found, will ask for input to choose one. Otherwise, will just grab everything. Defaults to False
- `anime_mappings`: Can provide custom mappings here. Otherwise, will use the Kometa mappings.
  The general user should not set this. Defaults to None
- `anidb_mappings`: Can provide custom mappings here. Otherwise, will use the AniDB mappings.
  The general user should not set this. Defaults to None
- `log_level`: Controls the level of logging. Can be WARNING, INFO, or DEBUG. Defaults to "INFO"

## Roadmap

- Currently, some episodes (particularly movies or OVAs) can be missed. This should be improved in the future by using
  more robust mapping between AniDB entries and AniList entries
- Support for other torrent clients
- Support for torrents on sites other than Nyaa
