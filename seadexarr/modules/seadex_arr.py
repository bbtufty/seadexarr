import copy
import json
import os
import shutil
from datetime import datetime
from hashlib import md5
from itertools import compress
from urllib.request import urlretrieve
from xml.etree import ElementTree

import httpx
import qbittorrentapi
import yaml
from ruamel.yaml import YAML
from seadex import SeaDexEntry, EntryNotFoundError

from .. import __version__
from .anilist import get_anilist_title, get_anilist_thumb
from .log import setup_logger, centred_string, left_aligned_string
from .torrent import (
    get_nyaa_url,
    get_animetosho_url,
    get_rutracker_url,
)


def save_json(
    data,
    out_file,
    sort_cache=False,
):
    """Save json in a pretty way

    Args:
        data (dict): Data to be saved
        out_file (str): Path to JSON file
        sort_cache (bool, optional): Whether to sort cache files by AniList ID. Defaults to False.
    """

    # Optionally sort this data
    if sort_cache:

        for arr, arr_item in data["anilist_entries"].items():
            keys = list(arr_item.keys())
            keys.sort(key=int)
            sorted_data = {key: arr_item[key] for key in keys}

            data["anilist_entries"][arr] = sorted_data

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            indent=4,
        )


ANIME_IDS_URL = "https://raw.githubusercontent.com/Kometa-Team/Anime-IDs/refs/heads/master/anime_ids.json"
ANIDB_MAPPINGS_URL = "https://raw.githubusercontent.com/Anime-Lists/anime-lists/refs/heads/master/anime-list-master.xml"
ANIBRIDGE_MAPPINGS_URL = "https://raw.githubusercontent.com/eliasbenb/PlexAniBridge-Mappings/refs/heads/v2/mappings.json"

ALLOWED_ARRS = [
    "radarr",
    "sonarr",
]

PUBLIC_TRACKERS = [
    "Nyaa",
    "AnimeTosho",
    "AniDex",
    "RuTracker",
]

PRIVATE_TRACKERS = [
    "AB",
    "BeyondHD",
    "PassThePopcorn",
    "BroadcastTheNet",
    "HDBits",
    "Blutopia",
    "Aither",
]

UPDATED_AT_STR_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_all_seadex_rgs_per_episode(
    seadex_dict,
    ep_list,
):
    """Get a list of all SeaDex releases per-episode

    Args:
        seadex_dict: Dictionary of SeaDex releases
        ep_list (list): List of episodes and info
    """

    all_seadex_rgs_per_episode = {"all": []}

    if len(seadex_dict) > 1:
        for seadex_rg, seadex_rg_item in seadex_dict.items():
            seadex_urls = seadex_rg_item.get("urls", {})
            for url, url_item in seadex_urls.items():

                seadex_episodes = url_item.get("episodes", [])

                # If we haven't managed to parse, then set this up as an
                # "all" episodes fallback
                if len(seadex_episodes) == 0:
                    if seadex_rg not in all_seadex_rgs_per_episode.get(seadex_rg, []):
                        all_seadex_rgs_per_episode["all"].append(seadex_rg)

                found_episodes = [False] * len(seadex_episodes)

                for seadex_idx, seadex_ep in enumerate(seadex_episodes):

                    if found_episodes[seadex_idx]:
                        continue

                    for sonarr_ep in ep_list:
                        sonarr_ep_season = sonarr_ep.get("seasonNumber", 999)
                        sonarr_ep_episode = sonarr_ep.get("episodeNumber", 999)

                        # Do we have a match?
                        if sonarr_ep_season == seadex_ep.get(
                            "season", 888
                        ) and sonarr_ep_episode == seadex_ep.get("episode", 888):

                            season_key = (
                                f"S{sonarr_ep_season:02d}E{sonarr_ep_episode:02d}"
                            )
                            if season_key not in all_seadex_rgs_per_episode:
                                all_seadex_rgs_per_episode[season_key] = []

                            if seadex_rg not in all_seadex_rgs_per_episode[season_key]:
                                all_seadex_rgs_per_episode[season_key].append(seadex_rg)

                            found_episodes[seadex_idx] = True

    return all_seadex_rgs_per_episode


class SeaDexArr:

    def __init__(
        self,
        arr="sonarr",
        config="config.yml",
        cache="cache.json",
        logger=None,
    ):
        """Base class for SeaDexArr instances

        Args:
            arr (str, optional): Which Arr is being run.
                Defaults to "sonarr".
            config (str, optional): Path to config file.
                Defaults to "config.yml".
            cache (str, optional): Path to cache file.
                Defaults to "cache.json".
            logger. Logging instance. Defaults to None,
                which will create one.
        """

        # If we don't have a config file, copy the sample to the current
        # working directory
        f_path = copy.deepcopy(__file__)
        config_template_path = os.path.join(
            os.path.dirname(f_path), "config_sample.yml"
        )
        if not os.path.exists(config):
            shutil.copy(config_template_path, config)
            raise FileNotFoundError(f"{config} not found. Copying template")

        self.config_file = config
        with open(config, "r") as f:
            self.config = yaml.safe_load(f)

        # Check the config has all the same keys as the sample, if not add 'em in
        self.verify_config(
            config_path=config,
            config_template_path=config_template_path,
        )

        # Ignore unmonitored flag
        self.ignore_unmonitored = self.config.get(f"{arr}_ignore_unmonitored", False)

        # qBit
        self.qbit = None
        qbit_info = self.config.get("qbit_info", None)

        # Check we've got everything we need
        qbit_info_provided = all(
            [qbit_info.get(key, None) is not None for key in qbit_info]
        )
        if qbit_info_provided:
            qbit = qbittorrentapi.Client(**qbit_info)

            # Ensure this works
            try:
                qbit.auth_log_in()
            except qbittorrentapi.LoginFailed:
                raise ValueError("qBittorrent login failed!")

            self.qbit = qbit

        self.ignore_seadex_update_times = self.config.get(
            "ignore_seadex_update_times", False
        )

        self.use_torrent_hash_to_filter = self.config.get(
            "use_torrent_hash_to_filter", False
        )

        # Hooks between torrents and Arrs, and torrent number bookkeeping
        self.torrent_category = self.config.get(f"{arr}_torrent_category", None)
        self.torrent_tags = self.config.get("torrent_tags", None)
        self.max_torrents_to_add = self.config.get("max_torrents_to_add", None)
        self.torrents_added = 0

        # Discord
        self.discord_url = self.config.get("discord_url", None)

        # Flags for filtering torrents
        self.public_only = self.config.get("public_only", True)
        self.prefer_dual_audio = self.config.get("prefer_dual_audio", True)
        self.want_best = self.config.get("want_best", True)

        ignore_tags = self.config.get("ignore_tags", None)
        if ignore_tags is None:
            ignore_tags = []
        self.ignore_tags = ignore_tags

        trackers = self.config.get("trackers", None)

        # If we don't have any trackers selected, build a list from public
        # and private trackers
        if trackers is None:
            trackers = copy.deepcopy(PUBLIC_TRACKERS)
            if not self.public_only:
                trackers += copy.deepcopy(PRIVATE_TRACKERS)

        self.trackers = [t.lower() for t in trackers]

        # Advanced settings
        self.sleep_time = self.config.get("sleep_time", 2)
        self.cache_time = self.config.get("cache_time", 1)

        # Get the mapping files
        anime_mappings = self.config.get("anime_mappings", None)
        anidb_mappings = self.config.get("anidb_mappings", None)
        anibridge_mappings = self.config.get("anibridge_mappings", None)

        if anime_mappings is None:
            anime_mappings = self.get_anime_mappings()
        if anidb_mappings is None:
            anidb_mappings = self.get_anidb_mappings()
        if anibridge_mappings is None:
            anibridge_mappings = self.get_anibridge_mappings()
        self.anime_mappings = anime_mappings
        self.anidb_mappings = anidb_mappings
        self.anibridge_mappings = anibridge_mappings

        self.interactive = self.config.get("interactive", False)

        if logger is None:
            log_level = self.config.get("log_level", "INFO")
            self.logger = setup_logger(log_level=log_level)
        else:
            self.logger = logger

        # Instantiate the SeaDex API
        self.seadex = SeaDexEntry()

        # Set up cache for AL API calls
        self.al_cache = {}

        # Load in cache, if it exists. Else create
        self.cache_file = cache
        if os.path.exists(cache):
            with open(cache, "r") as f:
                cache = json.load(f)
        else:
            cache = self.setup_cache()
        self.cache = cache

        # Check the package or config hasn't updated, else
        # edit the cache description
        self.check_cache_updates()

        self.log_line_sep = "="
        self.log_line_length = 80

    def verify_config(
        self,
        config_path,
        config_template_path,
    ):
        """Verify all the keys in the current config file match those in the template

        Args:
            config_path (str): Path to config file
            config_template_path (str): Path to config template
        """

        with open(config_template_path, "r") as f:
            config_template = YAML().load(f)

        # If the keys aren't in the right order, then
        # use the template as a base and inherit from
        # the main config
        if not list(self.config.keys()) == list(config_template.keys()):

            new_config = copy.deepcopy(config_template)
            for key in config_template.keys():
                if key in self.config:
                    new_config[key] = copy.deepcopy(self.config[key])
                else:
                    new_config[key] = copy.deepcopy(config_template[key])

            self.config = copy.deepcopy(new_config)

            # Save out
            with open(config_path, "w+") as f:
                YAML().dump(self.config, f)

        return True

    def setup_cache(self):
        """Set up the cache file"""

        cache = {}

        with open(self.config_file, "rb") as f:
            config_hash = md5(f.read()).hexdigest()

        # Descriptor for the file so we know if things have changed
        description = {
            "seadexarr_version": __version__,
            "config_checksum": config_hash,
        }

        cache.update({"description": description})
        cache.update({"anilist_entries": {}})

        return cache

    def check_cache_updates(self):
        """Check if anything's been updated, and if so update in cache"""

        # Check if SeaDexArr version has updated
        if (
            self.cache.get("description", {}).get("seadexarr_version", None)
            != __version__
        ):
            self.cache["description"]["seadexarr_version"] = __version__

        # Check if the config file has changed
        with open(self.config_file, "rb") as f:
            config_hash = md5(f.read()).hexdigest()
            if (
                self.cache.get("description", {}).get("config_checksum", None)
                != config_hash
            ):
                self.cache["description"]["config_checksum"] = config_hash

        return True

    def get_anime_mappings(self):
        """Get the anime IDs file"""

        anime_mappings_file = os.path.join("anime_ids.json")

        # If a file doesn't exist, get it
        self.get_external_mappings(
            f=anime_mappings_file,
            url=ANIME_IDS_URL,
        )

        with open(anime_mappings_file, "r") as f:
            anime_mappings = json.load(f)

        return anime_mappings

    def get_anidb_mappings(self):
        """Get the AniDB mappings file"""

        anidb_mappings_file = os.path.join("anime-list-master.xml")

        # If a file doesn't exist, get it
        self.get_external_mappings(
            f=anidb_mappings_file,
            url=ANIDB_MAPPINGS_URL,
        )

        anidb_mappings = ElementTree.parse(anidb_mappings_file).getroot()

        return anidb_mappings

    def get_anibridge_mappings(self):
        """Get PlexAniBridge mappings file"""

        anibridge_mappings_file = os.path.join("anibridge_mappings.json")

        # If a file doesn't exist, get it
        self.get_external_mappings(
            f=anibridge_mappings_file,
            url=ANIBRIDGE_MAPPINGS_URL,
        )

        with open(anibridge_mappings_file, "r") as f:
            anibridge_mappings = json.load(f)

        return anibridge_mappings

    def get_external_mappings(
        self,
        f,
        url,
    ):
        """Get an external mapping file, respecting a cache time

        Args:
            f (str): file on disk
            url (str): url to download the file from
        """

        if not os.path.exists(f):
            urlretrieve(url, f)

        # Check if this is older than the cache
        f_mtime = os.path.getmtime(f)
        f_datetime = datetime.fromtimestamp(f_mtime)
        now_datetime = datetime.now()

        # Get the time difference
        t_diff = now_datetime - f_datetime

        # If the file is older than the cache time, re-download
        if t_diff.days >= self.cache_time:
            urlretrieve(url, f)

        return True

    def get_seadex_entry(
        self,
        al_id,
    ):
        """Get SeaDex entry from AniList ID

        Args:
            al_id (int): AniList ID
        """

        sd_entry = None
        try:
            sd_entry = self.seadex.from_id(al_id)
        except EntryNotFoundError:
            pass
        except httpx.ConnectError:
            self.logger.warning("Could not connect to SeaDex. Website may be down")

        return sd_entry

    def check_al_id_in_cache(
        self,
        arr,
        al_id,
        seadex_entry,
    ):
        """Check if timestamps in cache match when SeaDex entry was last updated

        Args:
            arr (str): Arr instance
            al_id (int): AniList ID
            seadex_entry: SeaDex entry
        """
        sd_time = seadex_entry.updated_at
        sd_time_str = sd_time.strftime(UPDATED_AT_STR_FORMAT)
        cache_time = (
            self.cache.get("anilist_entries", {})
            .get(arr, {})
            .get(str(al_id), {})
            .get("updated_at")
        )

        return sd_time_str == cache_time

    def get_anilist_ids(
        self,
        tvdb_id=None,
        tmdb_id=None,
        imdb_id=None,
        tmdb_type="movie",
    ):
        """Get a list of entries that match on TVDB ID

        Args:
            tvdb_id (int): TVDB ID
            tmdb_id (int): TMDB ID
            imdb_id (int): IMDb ID
            tmdb_type (str): TMDB type. Can be "movie" or "show"
        """

        if tmdb_type not in ["movie", "show"]:
            raise ValueError("tmdb_type must be 'movie' or 'show'")

        # Check we have exactly one ID specified here
        non_none_sum = sum(v is not None for v in [tvdb_id, tmdb_id, imdb_id])

        if non_none_sum == 0:
            raise ValueError(
                "At least one of tvdb_id, tmdb_id, and imdb_id must be provided"
            )

        anilist_mappings = {}

        # Start by looking through our base case, which are the Kometa
        # Anime IDs. Save these to a dict where the key is the AniList ID
        anilist_mappings = self.get_mappings_from_anime_mappings(
            tvdb_id=tvdb_id,
            tmdb_id=tmdb_id,
            imdb_id=imdb_id,
            tmdb_type=tmdb_type,
            anilist_mappings=anilist_mappings,
        )

        # Then, look through the AniBridge mappings
        anilist_mappings = self.get_mappings_from_anibridge_mappings(
            tvdb_id=tvdb_id,
            tmdb_id=tmdb_id,
            imdb_id=imdb_id,
            tmdb_type=tmdb_type,
            anilist_mappings=anilist_mappings,
        )

        # Sort by AniList ID
        anilist_mappings = dict(sorted(anilist_mappings.items()))

        return anilist_mappings

    def get_mappings_from_anime_mappings(
        self,
        tvdb_id=None,
        tmdb_id=None,
        imdb_id=None,
        tmdb_type="movie",
        anilist_mappings=None,
    ):
        """Get mappings from the Anime ID mappings

        Args:
            tvdb_id (int): TVDB ID
            tmdb_id (int): TMDB ID
            imdb_id (int): IMDb ID
            tmdb_type (str): TMDB type. Can be "movie" or "show"
            anilist_mappings (dict): Dictionary of AniList mappings.
                Defaults to None, which will create a new dictionary
        """

        if anilist_mappings is None:
            anilist_mappings = {}

        if tmdb_type not in ["movie", "show"]:
            raise ValueError("tmdb_type must be 'movie' or 'show'")

        # Check we have exactly one ID specified here
        non_none_sum = sum(v is not None for v in [tvdb_id, tmdb_id, imdb_id])

        if non_none_sum == 0:
            raise ValueError(
                "At least one of tvdb_id, tmdb_id, and imdb_id must be provided"
            )

        if tvdb_id is not None:
            anilist_mappings.update(
                {
                    m["anilist_id"]: m
                    for n, m in self.anime_mappings.items()
                    if m.get("tvdb_id", None) == tvdb_id
                    and m.get("anilist_id", None) is not None
                    and m.get("anilist_id", None) not in anilist_mappings
                }
            )
        if tmdb_id is not None:
            anilist_mappings.update(
                {
                    m["anilist_id"]: m
                    for n, m in self.anime_mappings.items()
                    if m.get(f"tmdb_{tmdb_type}_id", None) == tmdb_id
                    and m.get("anilist_id", None) is not None
                    and m.get("anilist_id", None) not in anilist_mappings
                }
            )
        if imdb_id is not None:
            anilist_mappings.update(
                {
                    m["anilist_id"]: m
                    for n, m in self.anime_mappings.items()
                    if m.get("imdb_id", None) == imdb_id
                    and m.get("anilist_id", None) is not None
                    and m.get("anilist_id", None) not in anilist_mappings
                }
            )

        return anilist_mappings

    def get_mappings_from_anibridge_mappings(
        self,
        tvdb_id=None,
        tmdb_id=None,
        imdb_id=None,
        tmdb_type="movie",
        anilist_mappings=None,
    ):
        """Get mappings from the AniBridge mappings

        Args:
            tvdb_id (int): TVDB ID
            tmdb_id (int): TMDB ID
            imdb_id (int): IMDb ID
            tmdb_type (str): TMDB type. Can be "movie" or "show"
            anilist_mappings (dict): Dictionary of AniList mappings.
                Defaults to None, which will create a new dictionary
        """

        if anilist_mappings is None:
            anilist_mappings = {}

        if tmdb_type not in ["movie", "show"]:
            raise ValueError("tmdb_type must be 'movie' or 'show'")

        # Check we have exactly one ID specified here
        non_none_sum = sum(v is not None for v in [tvdb_id, tmdb_id, imdb_id])

        if non_none_sum == 0:
            raise ValueError(
                "At least one of tvdb_id, tmdb_id, and imdb_id must be provided"
            )

        if tvdb_id is not None:
            anilist_mappings.update(
                {
                    int(n): m
                    for n, m in self.anibridge_mappings.items()
                    if m.get("tvdb_id", None) == tvdb_id
                    and int(n) not in anilist_mappings
                }
            )
        if tmdb_id is not None:
            anilist_mappings.update(
                {
                    int(n): m
                    for n, m in self.anibridge_mappings.items()
                    if m.get(f"tmdb_{tmdb_type}_id", None) == tmdb_id
                    and int(n) not in anilist_mappings
                }
            )
        if imdb_id is not None:
            anilist_mappings.update(
                {
                    int(n): m
                    for n, m in self.anibridge_mappings.items()
                    if m.get("imdb_id", None) == imdb_id
                    and int(n) not in anilist_mappings
                }
            )

        return anilist_mappings

    def get_anilist_title(
        self,
        al_id,
        sd_entry,
    ):
        """Get the AniList title from an ID and the SeaDex entry

        Args:
            al_id (int): AniList ID
            sd_entry: SeaDex entry
        """

        anilist_title, self.al_cache = get_anilist_title(
            al_id,
            al_cache=self.al_cache,
        )

        self.log_al_title(
            anilist_title=anilist_title,
            sd_entry=sd_entry,
        )

        return anilist_title

    def get_seadex_dict(
        self,
        sd_entry,
    ):
        """Parse and filter SeaDex request

        Args:
            sd_entry: SeaDex API query
        """

        final_torrent_list = copy.deepcopy(sd_entry.torrents)

        # Filter out any tags
        final_torrent_list = [
            t  for t in final_torrent_list if len(set(self.ignore_tags).intersection(set(t.tags))) == 0
        ]

        # Filter down by allowed trackers
        final_torrent_list = [
            t for t in final_torrent_list if t.tracker.lower() in self.trackers
        ]

        # Filtering down to only public torrents
        if self.public_only:
            final_torrent_list = [
                t for t in final_torrent_list if t.tracker.is_public()
            ]

        # Pull out torrents tagged as best, so long as at least one
        # is tagged as best
        if self.want_best:
            any_best = any([t.is_best for t in final_torrent_list])
            if any_best:
                final_torrent_list = [t for t in final_torrent_list if t.is_best]

        # Now, if we prefer dual audio then remove any that aren't
        # tagged, so long as at least one is tagged
        if self.prefer_dual_audio:
            any_dual_audio = any([t.is_dual_audio for t in final_torrent_list])
            if any_dual_audio:
                final_torrent_list = [t for t in final_torrent_list if t.is_dual_audio]

        # Or, if it's False, do the opposite
        else:
            any_ja_audio = any([not t.is_dual_audio for t in final_torrent_list])
            if any_ja_audio:
                final_torrent_list = [
                    t for t in final_torrent_list if not t.is_dual_audio
                ]

        # Pull out release groups, URLs, and various other useful info as a
        # dictionary
        seadex_release_groups = {}
        for t in final_torrent_list:

            if t.release_group not in seadex_release_groups:
                seadex_release_groups[t.release_group] = {"urls": {}}
                seadex_release_groups[t.release_group]["tags"] = t.tags

            seadex_release_groups[t.release_group]["urls"][t.url] = {
                "url": t.url,
                "files": [f.name for f in t.files],
                "size": [f.size for f in t.files],
                "tracker": t.tracker,
                "hash": t.infohash,
                "download": False,
            }

        return seadex_release_groups

    def filter_seadex_interactive(
        self,
        seadex_dict,
        sd_entry,
    ):
        """If multiple matches are found, let the user filter them interactively

        Args:
            seadex_dict: Dictionary of SeaDex releases
            sd_entry: SeaDex entry
        """

        self.logger.warning(
            centred_string(
                f"Multiple releases found!:",
                total_length=self.log_line_length,
            )
        )
        self.logger.warning(
            left_aligned_string(
                f"Here are the SeaDex notes:",
                total_length=self.log_line_length,
            )
        )

        notes = sd_entry.notes.split("\n")
        for n in notes:
            self.logger.warning(
                left_aligned_string(
                    n,
                    total_length=self.log_line_length,
                )
            )
        self.logger.warning(
            left_aligned_string(
                "",
                total_length=self.log_line_length,
            )
        )

        all_srgs = list(seadex_dict.keys())
        for s_i, s in enumerate(all_srgs):
            self.logger.warning(
                left_aligned_string(
                    f"[{s_i}]: {s}",
                    total_length=self.log_line_length,
                )
            )

        srgs_to_grab = input(
            f"Which release do you want to grab? "
            f"Single number for one, comma separated list for multiple, or blank for all: "
        )

        srgs_to_grab = srgs_to_grab.split(",")

        # Remove any blank entries
        while "" in srgs_to_grab:
            srgs_to_grab.remove("")

        # If we have some selections, parse down
        if len(srgs_to_grab) > 0:
            seadex_dict_filtered = {}
            for srg_idx in srgs_to_grab:

                try:
                    srg = all_srgs[int(srg_idx)]
                except IndexError:
                    self.logger.warning(
                        left_aligned_string(
                            f"Index {srg_idx} is out of range",
                            total_length=self.log_line_length,
                        )
                    )
                    continue
                seadex_dict_filtered[srg] = copy.deepcopy(seadex_dict[srg])

            seadex_dict = copy.deepcopy(seadex_dict_filtered)

        return seadex_dict

    def get_seadex_fields(
        self,
        arr,
        al_id,
        release_group,
        seadex_dict,
    ):
        """Get fields for Discord post

        Args:
            arr: Type of arr instance
            al_id: AniList ID
            release_group: Arr release group
            seadex_dict: Dictionary of SeaDex releases
        """

        anilist_thumb, self.al_cache = get_anilist_thumb(
            al_id=al_id,
            al_cache=self.al_cache,
        )
        fields = []

        # The first field should be the Arr group. If it's empty, mention it's missing
        release_group_discord = copy.deepcopy(release_group)

        # Catch various edge cases
        if release_group_discord is None:
            release_group_discord = ["None"]
        if len(release_group_discord) == 0:
            release_group_discord = ["None"]
        if isinstance(release_group_discord, str):
            release_group_discord = [release_group]

        field_dict = {
            "name": f"{arr.capitalize()} Release:",
            "value": "\n".join(release_group_discord),
        }
        fields.append(field_dict)

        # SeaDex options with links
        for srg, srg_item in seadex_dict.items():

            # Check if we're actually downloading anything
            dl = [
                srg_item.get("urls", {}).get(x, {}).get("download", False)
                for x in srg_item["urls"]
            ]

            if any(dl):

                # Include any tags in the string
                discord_value = ""
                tags = srg_item.get("tags", [])
                if len(tags) > 0:
                    discord_value += "Tags:\n"
                    discord_value += "\n".join(tags)
                    discord_value += "\n\n"

                urls_to_download = [x for i, x in enumerate(srg_item["urls"]) if dl[i]]

                # And include URLs for files we're downloading
                discord_value += "Links:\n"
                discord_value += "\n".join(urls_to_download)

                field_dict = {
                    "name": f"SeaDex recommendation: {srg}",
                    "value": f"{discord_value}",
                }

                fields.append(field_dict)

        return fields, anilist_thumb

    def filter_seadex_downloads(
        self,
        al_id,
        seadex_dict,
        arr,
        arr_release_dict,
        ep_list=None,
    ):
        """Flip the switch on whether we're downloading this torrent or not

        Args:
            al_id: AniList ID
            seadex_dict: Dictionary of SeaDex releases
            arr: Type of arr instance
            arr_release_dict: Dictionary of arr release properties
            ep_list: List of episodes. Defaults to None
        """

        if self.use_torrent_hash_to_filter:
            torrent_hashes, seadex_dict = self.filter_by_torrent_hash(
                al_id=al_id,
                seadex_dict=seadex_dict,
                arr=arr,
            )
        else:
            torrent_hashes, seadex_dict = self.filter_by_release_group(
                seadex_dict=seadex_dict,
                arr=arr,
                arr_release_dict=arr_release_dict,
                ep_list=ep_list,
            )

            # Also include any cached hashes
            cached_hashes = (
                self.cache.get("anilist_entries", {})
                .get(arr, {})
                .get(str(al_id), {})
                .get("torrent_hashes", [])
            )
            torrent_hashes.extend(cached_hashes)

        # Make sure the hashes are unique
        torrent_hashes = list(set(torrent_hashes))

        return torrent_hashes, seadex_dict

    def filter_by_torrent_hash(
        self,
        al_id,
        seadex_dict,
        arr,
    ):
        """Select downloads if torrent hash is not already in cache

        Note that for multiple "best" releases, this means everything will
        be grabbed

        Args:
            al_id: AniList ID
            seadex_dict: Dictionary of SeaDex releases
            arr: Type of arr instance
        """

        cached_hashes = (
            self.cache.get("anilist_entries", {})
            .get(arr, {})
            .get(str(al_id), {})
            .get("torrent_hashes", [])
        )
        torrent_hashes = []

        for seadex_rg, seadex_rg_item in seadex_dict.items():

            self.logger.debug(
                left_aligned_string(
                    f"Filtering for release group {seadex_rg}",
                    total_length=self.log_line_length,
                )
            )

            seadex_urls = seadex_rg_item.get("urls", {})
            for url, url_item in seadex_urls.items():

                url_hash = url_item.get("hash", None)

                # If the URL is already in the hash cache, then append but don't set to download
                torrent_hashes.append(url_hash)
                if url_hash not in cached_hashes:
                    self.logger.debug(
                        left_aligned_string(
                            f"Torrent hash {url_hash} not found in cache. "
                            f"Will add to downloads",
                            total_length=self.log_line_length,
                        )
                    )

                    url_item.update({"download": True})

                else:
                    self.logger.debug(
                        left_aligned_string(
                            f"Torrent hash {url_hash} in cache. " f"Will skip download",
                            total_length=self.log_line_length,
                        )
                    )

        return torrent_hashes, seadex_dict

    def filter_by_release_group(
        self,
        seadex_dict,
        arr,
        arr_release_dict,
        ep_list=None,
    ):
        """Filter torrents by release group

        This is either episode-by-episode for the Sonarr
        case where we can parse episodes, or a more blunt
        hammer just checking against anything for Radarr
        and weirdly named TV

        Args:
            seadex_dict: Dictionary of SeaDex releases
            arr: Type of arr instance
            arr_release_dict: Dictionary of arr release properties
            ep_list: List of episodes. Defaults to None
        """

        # Get a simple list of the release groups
        arr_release_groups = list(arr_release_dict.keys())

        torrent_hashes = []

        # And also just check if any release group matches
        # any Arr release tag
        overlapping_results = False
        intersect = list(
            filter(
                lambda x: x in list(seadex_dict.keys()),
                arr_release_groups,
            )
        )
        if len(intersect) > 0:
            overlapping_results = True

        # If we have overlaps, get a note of them here
        all_seadex_rgs_per_episode = get_all_seadex_rgs_per_episode(
            seadex_dict=seadex_dict,
            ep_list=ep_list,
        )

        for seadex_rg, seadex_rg_item in seadex_dict.items():

            self.logger.debug(
                left_aligned_string(
                    f"Filtering for release group {seadex_rg}",
                    total_length=self.log_line_length,
                )
            )

            seadex_urls = seadex_rg_item.get("urls", {})
            for url, url_item in seadex_urls.items():

                url_hash = url_item.get("hash", None)
                seadex_episodes = url_item.get("episodes", [])

                # Simple case, we have no episode mappings so
                # just fall back to checking against release group
                if len(seadex_episodes) == 0:
                    if seadex_rg not in arr_release_groups and not overlapping_results:
                        self.logger.debug(
                            left_aligned_string(
                                f"SeaDex release group {seadex_rg} not in {arr.capitalize()} release(s): "
                                f"{','.join([str(x) for x in arr_release_groups])}. "
                                f"Will add {url} to downloads",
                                total_length=self.log_line_length,
                            )
                        )

                        url_item.update({"download": True})
                        torrent_hashes.append(url_hash)

                    # Else, if we match then double-check against the size
                    if seadex_rg in arr_release_groups:

                        # Be a blunt hammer and just check intersections
                        seadex_file_sizes = url_item.get("size", [])
                        arr_file_sizes = arr_release_dict[seadex_rg].get("size", [])

                        if not isinstance(arr_file_sizes, list):
                            arr_file_sizes = [arr_file_sizes]

                        intersect = list(
                            filter(
                                lambda x: x in seadex_file_sizes,
                                arr_file_sizes,
                            )
                        )

                        # If we have no overlaps at all, then add
                        if len(intersect) == 0:
                            self.logger.info(
                                left_aligned_string(
                                    f"SeaDex release group {seadex_rg} in {arr.capitalize()} release(s): "
                                    f"{','.join([str(x) for x in arr_release_groups])}, but filesizes do not match. "
                                    f"Will add {url} to downloads",
                                    total_length=self.log_line_length,
                                )
                            )

                            url_item.update({"download": True})
                            torrent_hashes.append(url_hash)

                        else:
                            self.logger.debug(
                                left_aligned_string(
                                    f"SeaDex release group {seadex_rg} in {arr.capitalize()} release(s): "
                                    f"{','.join([str(x) for x in arr_release_groups])}, and filesizes match. ",
                                    total_length=self.log_line_length,
                                )
                            )

                else:

                    # At this point, we need an episode list from Sonarr
                    if ep_list is None:
                        self.logger.warning(
                            "If checking against individual episodes, you need to pass the Sonarr ep_list"
                        )
                        continue

                    # For each episode we've parsed from the torrent, check if a) it exists in the Sonarr list, b) if
                    # the release group matches, and c) if the filesizes match. If there's any mismatch between release
                    # groups (and there's no alternatives), then flip download to True. If all the sizes mismatch,
                    # flip download to true

                    found_episodes = [False] * len(seadex_episodes)
                    rg_matches = [False] * len(seadex_episodes)
                    size_matches = [False] * len(seadex_episodes)

                    for seadex_idx, seadex_ep in enumerate(seadex_episodes):

                        if found_episodes[seadex_idx]:
                            continue

                        for sonarr_ep in ep_list:

                            # Get Season, Episode, and size numbers for Sonarr and SeaDex
                            sonarr_ep_season = sonarr_ep.get("seasonNumber", 999)
                            sonarr_ep_episode = sonarr_ep.get("episodeNumber", 999)
                            sonarr_ep_size = sonarr_ep.get("episodeFile", {}).get(
                                "size", None
                            )

                            seadex_ep_season = seadex_ep.get("season", 888)
                            seadex_ep_episode = seadex_ep.get("episode", 888)
                            seadex_ep_size = seadex_ep.get("size", None)

                            # Do we have a match?
                            if (
                                sonarr_ep_season == seadex_ep_season
                                and sonarr_ep_episode == seadex_ep_episode
                            ):

                                # Do the sizes match?
                                size_match = sonarr_ep_size == seadex_ep_size

                                season_ep_str = (
                                    f"S{sonarr_ep_season:02d}E{sonarr_ep_episode:02d}"
                                )

                                # Check SeaDex release group matches the episode release group in Sonarr
                                sonarr_rg = sonarr_ep.get("episodeFile", {}).get(
                                    "releaseGroup", None
                                )

                                # If not, flag as should be downloaded if it's not already
                                # in some overlapping release
                                if (
                                    sonarr_rg != seadex_rg
                                    and sonarr_rg
                                    not in all_seadex_rgs_per_episode["all"]
                                ):

                                    # This check here is to make sure we don't duplicate
                                    # if there's overlap
                                    all_seadex_rg = all_seadex_rgs_per_episode.get(
                                        season_ep_str, []
                                    )

                                    if sonarr_rg not in all_seadex_rg:
                                        self.logger.debug(
                                            left_aligned_string(
                                                f"SeaDex release group {seadex_rg} not the same as "
                                                f"{arr.capitalize()} release for "
                                                f"{season_ep_str} {sonarr_rg}, "
                                                f"and does not match any other suitable releases. "
                                                f"Will add {url} to downloads",
                                                total_length=self.log_line_length,
                                            )
                                        )

                                        url_item.update({"download": True})
                                        torrent_hashes.append(url_hash)

                                else:

                                    self.logger.debug(
                                        left_aligned_string(
                                            f"Found SeaDex match to {arr.capitalize()} "
                                            f"for {season_ep_str}.",
                                            total_length=self.log_line_length,
                                        )
                                    )
                                    if not size_match:
                                        self.logger.debug(
                                            left_aligned_string(
                                                f"-> Sizes are different: "
                                                f"{sonarr_ep_size} (Sonarr), {seadex_ep_size} (SeaDex)",
                                                total_length=self.log_line_length,
                                            )
                                        )
                                    else:
                                        self.logger.debug(
                                            left_aligned_string(
                                                f"-> Sizes match: {sonarr_ep_size}",
                                                total_length=self.log_line_length,
                                            )
                                        )

                                    rg_matches[seadex_idx] = True

                                # Now check against file size
                                if size_match:
                                    size_matches[seadex_idx] = True

                                found_episodes[seadex_idx] = True

                    # If we have matched the release groups but not the file sizes, then flag that
                    # here and mark for download
                    size_matches = list(compress(size_matches, rg_matches))
                    if not any(size_matches) and len(size_matches) > 0:
                        self.logger.info(
                            left_aligned_string(
                                f"File sizes are all different for release group {seadex_rg}. "
                                f"Will add {url} to downloads",
                                total_length=self.log_line_length,
                            )
                        )
                        url_item.update({"download": True})

        return torrent_hashes, seadex_dict

    @staticmethod
    def get_any_to_download(seadex_dict):
        """Check if any torrents are marked as to download

        Args:
            seadex_dict (dict): Dictionary of SeaDex releases
        """

        any_to_download = False
        for rg in seadex_dict:

            if any_to_download:
                return any_to_download

            dl = [
                seadex_dict[rg]["urls"][x].get("download", False)
                for x in seadex_dict[rg]["urls"]
            ]
            if any(dl):
                any_to_download = True

        return any_to_download

    def add_torrent(
        self,
        torrent_dict,
        torrent_client="qbit",
    ):
        """Add torrent(s) to a torrent client

        Args:
            torrent_dict (dict): Dictionary of torrent info
            torrent_client (str): Torrent client to use. Options are
                "qbit" for qBittorrent. Defaults to "qbit"
        """

        n_torrents_added = 0

        for srg, srg_item in torrent_dict.items():

            self.logger.info(
                left_aligned_string(
                    f"Adding torrent(s) for group {srg} to {torrent_client}",
                    total_length=self.log_line_length,
                )
            )

            seadex_urls = srg_item.get("urls", {})
            for url, url_item in seadex_urls.items():

                # If not flagged for download, then skip
                download = url_item.get("download", False)
                if not download:
                    continue

                item_hash = url_item.get("hash", None)
                tracker = url_item.get("tracker", None)

                # If we don't have a tracker from our list selected, then
                # get out of here
                if tracker.lower() not in self.trackers:
                    self.logger.info(
                        left_aligned_string(
                            f"   Skipping {url} as tracker {tracker} not in selected list",
                            total_length=self.log_line_length,
                        )
                    )
                    continue

                # Nyaa
                if tracker.lower() == "nyaa":
                    parsed_url = get_nyaa_url(url=url)

                # AnimeTosho
                elif tracker.lower() == "animetosho":
                    parsed_url = get_animetosho_url(url=url)

                # RuTracker
                elif tracker.lower() == "rutracker":
                    parsed_url = get_rutracker_url(
                        url=url,
                        torrent_hash=item_hash,
                    )

                # Otherwise, bug out
                else:
                    raise ValueError(f"Unable to parse torrent links from {tracker}")

                if parsed_url is None:
                    raise Exception("Have not managed to parse the torrent URL")

                if torrent_client == "qbit":
                    success = self.add_torrent_to_qbit(
                        url=url,
                        torrent_url=parsed_url,
                        torrent_hash=item_hash,
                    )

                else:
                    raise ValueError(f"Unsupported torrent client {torrent_client}")

                if success == "torrent_added":
                    self.logger.info(
                        left_aligned_string(
                            f"   Added {parsed_url} to {torrent_client}",
                            total_length=self.log_line_length,
                        )
                    )

                    # Increment the number of torrents added, and if we've hit the limit then
                    # jump out
                    self.torrents_added += 1
                    n_torrents_added += 1
                    if self.max_torrents_to_add is not None:
                        if self.torrents_added >= self.max_torrents_to_add:
                            return n_torrents_added

                elif success == "torrent_already_added":
                    self.logger.info(
                        left_aligned_string(
                            f"   Torrent already in {torrent_client}",
                            total_length=self.log_line_length,
                        )
                    )

                else:
                    raise ValueError(f"Cannot handle torrent client {torrent_client}")

        return n_torrents_added

    def add_torrent_to_qbit(
        self,
        url,
        torrent_url,
        torrent_hash,
    ):
        """Add a torrent to qbittorrent

        Args:
            url (str): SeaDex URL
            torrent_url (str): Torrent URL to add to client
            torrent_hash (str): Torrent hash
        """

        # Ensure we don't already have the hash in there
        torr_info = self.qbit.torrents_info(torrent_hashes=torrent_hash)
        torr_hashes = [i.hash for i in torr_info]

        if torrent_hash in torr_hashes:
            self.logger.debug(
                centred_string(
                    f"Torrent {url} already in qBittorrent",
                    total_length=self.log_line_length,
                )
            )
            return "torrent_already_added"

        # Add the torrent
        result = self.qbit.torrents_add(
            urls=torrent_url,
            category=self.torrent_category,
            tags=self.torrent_tags,
        )
        if result != "Ok.":
            raise Exception("Failed to add torrent")

        return "torrent_added"

    def update_cache(self, arr, al_id, cache_details=None):
        """Update cache with useful info

        Args:
            arr (str): Arr instance
            al_id (int): AniList ID
            cache_details (dict): Details for the cache entry.
                Defaults to None
        """

        if cache_details is None:
            cache_details = {}

        # Turn datetime to string
        if "updated_at" in cache_details:
            cache_details["updated_at"] = cache_details["updated_at"].strftime(
                UPDATED_AT_STR_FORMAT
            )

        # Add to cache and save out
        if arr not in self.cache["anilist_entries"]:
            self.cache["anilist_entries"][arr] = {}

        if str(al_id) not in self.cache["anilist_entries"][arr]:
            self.cache["anilist_entries"][arr][str(al_id)] = {}

        self.cache["anilist_entries"][arr][str(al_id)].update(cache_details)
        save_json(
            self.cache,
            self.cache_file,
            sort_cache=True,
        )

        return True

    def log_arr_start(
        self,
        arr,
        n_items,
    ):
        """Produce a log message for the start of the run

        Args:
            arr: Type of arr instance
            n_items: Total number of shows/movies
        """

        if arr not in ALLOWED_ARRS:
            raise ValueError(f"arr must be one of: {ALLOWED_ARRS}")

        item_type = {
            "radarr": "movies",
            "sonarr": "series",
        }[arr]

        self.logger.info(
            centred_string(
                self.log_line_sep * self.log_line_length,
                total_length=self.log_line_length,
            )
        )
        self.logger.info(
            centred_string(
                f"Starting SeaDex-{arr.capitalize()} for {n_items} {item_type}",
                total_length=self.log_line_length,
            )
        )
        self.logger.info(
            centred_string(
                self.log_line_sep * self.log_line_length,
                total_length=self.log_line_length,
            )
        )

        return True

    def log_arr_item_unmonitored(
        self,
        arr,
        item_title,
    ):
        """Produce a log message if skipping because item is unmonitored

        Args:
            arr: Type of arr instance
            item_title (str): Item title
        """

        self.logger.info(
            centred_string(
                f"{item_title} is unmonitored in {arr.capitalize()}",
                total_length=self.log_line_length,
            )
        )

        self.logger.info(
            centred_string(
                self.log_line_sep * self.log_line_length,
                total_length=self.log_line_length,
            )
        )

        return True

    def log_anilist_item_unmonitored(
        self,
        arr,
        item_title,
    ):
        """Produce a log message if skipping an AniList item because it's unmonitored in Sonarr

        Args:
            arr: Type of arr instance
            item_title (str): Item title
        """

        self.logger.info(
            centred_string(
                f"{item_title} is unmonitored in {arr.capitalize()}",
                total_length=self.log_line_length,
            )
        )

        self.logger.info(
            centred_string(
                "-" * self.log_line_length,
                total_length=self.log_line_length,
            )
        )

        return True

    def log_arr_item_start(
        self,
        arr,
        item_title,
        n_item,
        n_items,
    ):
        """Produce a log message for the start of Arr item

        Args:
            arr: Type of arr instance
            item_title: Title for the item
            n_item: Number for the show/movie
            n_items: Total number of shows/movies
        """

        self.logger.info(
            centred_string(
                self.log_line_sep * self.log_line_length,
                total_length=self.log_line_length,
            )
        )
        self.logger.info(
            centred_string(
                f"[{n_item}/{n_items}] {arr.capitalize()}: {item_title}",
                total_length=self.log_line_length,
            )
        )
        self.logger.info(
            centred_string(
                "-" * self.log_line_length,
                total_length=self.log_line_length,
            )
        )

        return True

    def log_no_anilist_mappings(
        self,
        title,
    ):
        """Produce a log message for the case where no AniList mappings are found

        Args:
            title: Title for the item
        """

        self.logger.warning(
            centred_string(
                f"No AniList mappings found for {title}. Skipping",
                total_length=self.log_line_length,
            )
        )
        self.logger.info(
            centred_string(
                self.log_line_sep * self.log_line_length,
                total_length=self.log_line_length,
            )
        )

        return True

    def log_no_anilist_id(self):
        """Produce a log message for the case where no AniList ID is found"""

        self.logger.debug(
            centred_string(
                f"-> No AL ID found. Continuing",
                total_length=self.log_line_length,
            )
        )
        self.logger.debug(
            centred_string(
                "-" * self.log_line_length,
                total_length=self.log_line_length,
            )
        )

        return True

    def log_no_sd_entry(
        self,
        al_id,
    ):
        """Produce a log message if no SeaDex entry is found

        Args:
            al_id (int): Al ID
        """

        self.logger.debug(
            centred_string(
                f"No SeaDex entry found for AniList ID {al_id}. Continuing",
                total_length=self.log_line_length,
            )
        )
        self.logger.debug(
            centred_string(
                "-" * self.log_line_length,
                total_length=self.log_line_length,
            )
        )

        return True

    def log_al_title(
        self,
        anilist_title,
        sd_entry,
    ):
        """Produce a log message for the AniList title, with URL and notice if incomplete

        Args:
            anilist_title (str): Title for the AniList
            sd_entry: SeaDex entry
        """

        sd_url = sd_entry.url
        is_incomplete = sd_entry.is_incomplete

        # Get a string, marking if things are incomplete
        al_str = f"AniList: {anilist_title} ({sd_url})"
        if is_incomplete:
            al_str += f" [MARKED INCOMPLETE]"

        self.logger.info(
            centred_string(
                al_str,
                total_length=self.log_line_length,
            )
        )

        return True

    def log_no_seadex_releases(self):
        """Log if no suitable SeaDex releases are found"""

        self.logger.info(
            centred_string(
                f"No suitable releases found on SeaDex",
                total_length=self.log_line_length,
            )
        )
        self.logger.info(
            centred_string(
                "-" * self.log_line_length,
                total_length=self.log_line_length,
            )
        )

        return True

    def log_arr_seadex_mismatch(
        self,
        arr,
        seadex_dict,
    ):
        """Log out there's a mismatch between the Arr releases and the SeaDex recommendations

        Args:
            arr: Type of arr instance
            seadex_dict (dict): Dictionary of SeaDex entries
        """

        if arr not in ALLOWED_ARRS:
            raise ValueError(f"arr must be one of: {ALLOWED_ARRS}")

        item_type = {
            "radarr": "movie",
            "sonarr": "series",
        }[arr]

        self.logger.info(
            centred_string(
                f"Mismatch found between SeaDex recommendation and existing {arr.capitalize()} {item_type}!",
                total_length=self.log_line_length,
            )
        )
        self.logger.info(
            centred_string(
                f"SeaDex recommended version(s):",
                total_length=self.log_line_length,
            )
        )

        # SeaDex options with links
        for srg, srg_item in seadex_dict.items():

            dl = [
                srg_item.get("urls", {}).get(x, {}).get("download", False)
                for x in srg_item.get("urls", {})
            ]
            if any(dl):
                self.logger.info(
                    left_aligned_string(
                        f"{srg}:",
                        total_length=self.log_line_length,
                    )
                )
                tags = srg_item.get("tags", [])
                if len(tags) > 0:
                    self.logger.info(
                        left_aligned_string(
                            f"   Tags: {','.join([t for t in tags])}",
                            total_length=self.log_line_length,
                        )
                    )
                for url in srg_item.get("urls", {}):

                    download = (
                        srg_item.get("url", {}).get(url, {}).get("download", False)
                    )
                    if download:
                        self.logger.info(
                            left_aligned_string(
                                f"   {url}",
                                total_length=self.log_line_length,
                            )
                        )

        return True

    def log_max_torrents_added(self):
        """Produce a log message about hitting maximum number of torrents added"""

        self.logger.info(
            centred_string(
                "Added maximum number of torrents for this run. Stopping",
                total_length=self.log_line_length,
            )
        )
        self.logger.info(
            centred_string(
                self.log_line_sep * self.log_line_length,
                total_length=self.log_line_length,
            )
        )

        return True
