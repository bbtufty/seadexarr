# SeaDexArr

[![](https://img.shields.io/pypi/v/seadexarr.svg?label=PyPI&style=flat-square)](https://pypi.org/pypi/seadexarr/)
[![](https://img.shields.io/pypi/pyversions/seadexarr.svg?label=Python&color=yellow&style=flat-square)](https://pypi.org/pypi/seadexarr/)
[![Actions](https://img.shields.io/github/actions/workflow/status/bbtufty/seadexarr/build.yaml?branch=main&style=flat-square)](https://github.com/bbtufty/seadexarr/actions)
[![License](https://img.shields.io/badge/license-GNUv3-blue.svg?label=License&style=flat-square)](LICENSE)

![SeaDexArr](example_post.png)

SeaDexArr is designed as a tool to ensure that you have Anime releases on the Arr apps that match with the best 
releases tagged on SeaDex. SeaDexArr supports both Sonarr and Radarr.

For Sonarr, it works by scanning through series, matching these up via the TVDB or IMDb IDs to AniList 
mappings via the Kometa Anime Mappings (https://github.com/Kometa-Team/Anime-IDs), AniDB mappings 
(https://github.com/Anime-Lists/anime-lists), and ultimately finding releases in the SeaDex database. For Radarr, this 
works much the same but instead using the TMDB and IMDb IDs. 

SeaDexArr will then do some cuts to select a "best" release, which can be pushed to Discord via a bot, and added
automatically to a torrent client. This should make it significantly more hands-free to keep the best Anime releases 
out there.

There are then two options for how SeaDexArr will filter releases to grab:

Against existing files (default; `use_torrent_hash_to_filter = False`):

SeaDexArr will attempt to match these releases to release groups in Sonarr/Radarr, and for Sonarr will also try to
parse filenames to check against individual episodes. SeaDexArr also checks against filesizes, to attempt to catch when 
release groups put out updated releases, or those at higher quality.

Against torrent hashes (`use_torrent_hash_to_filter = True`):

SeaDexArr will match releases to torrent hashes in the cache. This will ensure that if releases get updated then they
will be grabbed. However, if you already have an existing library then this could result in torrents being downloaded
again, and will grab multiple overlapping results if you aren't in interactive mode.

By default, SeaDexArr will not check a particular release again unless SeaDex has updated recently. You can override
this behaviour by setting ``ignore_seadex_update_times`` to True in the config (see config section below).

> [!TIP]
> **If you make changes to your config, you should probably remove your cache. You can do so by CLI,
> use ``seadexarr cache remove`` (see below for more details).**

## Installation

SeaDexArr is available as a Docker container. Into a docker-compose file:

```
services:

  seadexarr:
    image: ghcr.io/bbtufty/seadexarr:latest  # or seadexarr:main for the cutting edge
    container_name: seadexarr
    environment: 
      - SCHEDULE_TIME=6  # How often to run, in hours
    volumes:
      - /path/to/config:/config
    restart: unless-stopped
```

And then to run on a schedule, simply run `docker-compose up -d seadexarr`. If you want to run one Arr one time, you 
can instead run like `docker-compose run seadexarr run single --radarr --sonarr`.

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

## CLI

SeaDexArr features a command-line interface, with a number of modules. If running in Docker mode, 
to run these simply add a ``docker run`` before the command below.

### ``seadexarr run``

There are two options here, ``run scheduled`` and ``run single``. Scheduled is the default mode,
and will run if you just enter ``seadexarr`` into the command line, which will run every few hours
(default 6) to keep things up to date automatically. Single will just run once and be done. For
the single run, pass --sonarr or --radarr to run the Sonarr or Radarr modules. Scheduled runs
automatically for both

### ``seadexarr config``

To generate a blank config file, simply enter ``config init``. You can then populate
to your liking.

### ```seadexarr cache```

There are a number of cache commands: ``cache backup`` will rename ``cache.json`` to ``cache.backup.json``,
``cache restore`` will restore this backup, and ``cache remove`` will remove the cache file. This can
be useful if you've changed the config and want to do a fresh run.

## Scripting

To run SeaDexArr in a Python script, the code is simple:

```
from seadexarr import SeaDexSonarr, SeaDexRadarr

sds = SeaDexSonarr()
sds.run()

sdr = SeaDexRadarr()
sdr.run()
```

On the first run, the code will generate a config file in your working directory. This should be populated to your own 
preference, and then run the code again.

## How SeaDexArr chooses a release

SeaDexArr performs a number of cuts to get to a single best release for you. First, it will filter out all torrents
coming from trackers that haven't been specified (if you haven't been more granular, this will be all public trackers
and potentially all private trackers; see ``trackers``). Then, if you only want public torrents (``public_only``), it
will filter out anything from a private tracker. Next, if you only want to grab releases marked by SeaDex as "best"
(``want_best``), it will down-select any torrents marked as "best", as long as there's at least one. Finally, if
you want dual audio (``prefer_dual_audio``), it will down-select any dual-audio torrents, as long as there's at least
one. If this is instead set to ``False``, it will do the opposite, filtering out any dual-audio torrents (so long
as there's at least one not tagged as dual-audio). By doing this, SeaDexArr should generally find a single best
torrent, though if you're in interactive mode (``interactive``) and there are multiple options that match your
criteria, it will give you an option to select one (or multiple).

## Config

There are a number of configuration settings to play around with. These should be self-explanatory, but a more detailed
description of each is given below.

### Arr settings

- `sonarr_url`: URL for Sonarr. Required if running SeaDexSonarr
- `sonarr_api_key`: API key for Sonarr (Settings/General/API Key). Required if running SeaDexSonarr
- `ignore_movies_in_radarr`: If True, will not add releases found in Sonarr (movie specials) if they already
  exist as movies in Radarr. Defaults to False

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
- `prefer_dual_audio`: Prefer results tagged as dual audio, if any exist. If False, will instead prefer Ja-only 
  releases. Defaults to True
- `want_best`: Prefer results tagged as best, if any exist. Defaults to True
- `trackers`: Can manually select a list of trackers. Defaults to None, which will use all the 
  public trackers and private trackers if `public_only` is False. All trackers with torrents on SeaDex, and whether 
  they are supported are below.
  - Public trackers
    - Nyaa (supported)
    - AnimeTosho (supported)
    - AniDex
    - RuTracker (supported)
  - Private trackers
    - AB
    - BeyondHD
    - PassThePopcorn
    - HDBits
    - Blutopia
    - Aither

### Advanced settings

- `ignore_seadex_update_times`: If True, will not check against the update times in the cache to
  decide whether to search for a release. Defaults to False
- `use_torrent_hash_to_filter`: Can either try and filter by release groups in Sonarr/Radarr (False),
  or by torrent hashes in the cache (True). Defaults to False. See a more detailed description above
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
- Support for more torrent sites
