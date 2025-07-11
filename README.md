# SeaDex-Sonarr

[![](https://img.shields.io/pypi/v/seadex_sonarr.svg?label=PyPI&style=flat-square)](https://pypi.org/pypi/seadex_sonarr/)
[![](https://img.shields.io/pypi/pyversions/seadex_sonarr.svg?label=Python&color=yellow&style=flat-square)](https://pypi.org/pypi/seadex_sonarr/)
[![Actions](https://img.shields.io/github/actions/workflow/status/bbtufty/seadex-sonarr/build.yaml?branch=main&style=flat-square)](https://github.com/bbtufty/seadex-sonarr/actions)
[![License](https://img.shields.io/badge/license-GNUv3-blue.svg?label=License&style=flat-square)](LICENSE)

![SeaDex-Sonarr](example_post.png)

SeaDex-Sonarr is designed as a tool to ensure that you have Anime releases on Sonarr that match with the best releases
tagged on SeaDex. It works by scanning through series tagged as type "Anime" on Sonarr, matching these up via the TVDB
ID to AniList mappings via the Kometa Anime Mappings (https://github.com/Kometa-Team/Anime-IDs), and then linking 
these through to SeaDex. It then returns a list of links to download, which can also optionally be pushed through
via a Discord bot. This should make it significantly more hands-free to keep the best Anime releases out there.

## Installation

SeaDex-Sonarr can be installed via pip:

```
pip install seadex_sonarr
```

Or the cutting edge via GitHUb:

```
git clone https://github.com/bbtufty/seadex-sonarr.git
cd seadex-sonarr
pip install -e .
```

## Usage

To run SeaDex-Sonarr, the Python code is pretty short:

```
from seadex_sonarr import SeaDexSonarr

sonarr_url = "your-sonarr-url:8989"
sonarr_api_key = "abcdefg12345"

sds = SeaDexSonarr(sonarr_url=sonarr_url, 
                   sonarr_api_key=sonarr_api_key
                   )
sds.run()
```

If you want to use Discord notifications (recommended), then set up a webhook following 
[this guide](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks) and add the URL into the call:

```
from seadex_sonarr import SeaDexSonarr

sonarr_url = "your-sonarr-url:8989"
sonarr_api_key = "abcdefg12345"
discord_url = "https://discord.com/api/webhooks/abcde12345"

sds = SeaDexSonarr(sonarr_url=sonarr_url, 
                   sonarr_api_key=sonarr_api_key,
                   discord_url=discord_url,
                   )
sds.run()
```

## Advanced Settings

There are a number of switches you can use to filter down what SeaDex-Sonarr returns as the "best" option for you. These 
are:

- `public_only` (defaults to True), will only return results
  from public trackers
- `prefer_dual_audio` (defaults to True), will prefer results
  tagged as dual audio, if any exist
- `want_best` (defaults to True), will prefer results tagged
  as best, if any exist
