import copy
import json
import os
import shutil
from datetime import datetime
from urllib.request import urlretrieve
from xml.etree import ElementTree

import qbittorrentapi
import yaml
from ruamel.yaml import YAML
from seadex import SeaDexEntry, EntryNotFoundError

from .anilist import get_anilist_title, get_anilist_thumb
from .log import setup_logger, centred_string, left_aligned_string
from .torrent import get_nyaa_url, get_animetosho_url

ANIME_IDS_URL = "https://raw.githubusercontent.com/Kometa-Team/Anime-IDs/refs/heads/master/anime_ids.json"
ANIDB_MAPPINGS_URL = "https://raw.githubusercontent.com/Anime-Lists/anime-lists/refs/heads/master/anime-list-master.xml"

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


class SeaDexArr:

    def __init__(
        self,
        arr="sonarr",
        config="config.yml",
        logger=None,
    ):
        """Base class for SeaDexArr instances

        Args:
            arr (str, optional): Which Arr is being run.
                Defaults to "sonarr".
            config (str, optional): Path to config file.
                Defaults to "config.yml".
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

        with open(config, "r") as f:
            self.config = yaml.safe_load(f)

        # Check the config has all the same keys as the sample, if not add 'em in
        self.verify_config(
            config_path=config,
            config_template_path=config_template_path,
        )

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

        # Hooks between torrents and Arrs, and torrent number bookkeeping
        self.torrent_category = self.config.get(f"{arr}_torrent_category", None)
        self.max_torrents_to_add = self.config.get("max_torrents_to_add", None)
        self.torrents_added = 0

        # Discord
        self.discord_url = self.config.get("discord_url", None)

        # Flags for filtering torrents
        self.public_only = self.config.get("public_only", True)
        self.prefer_dual_audio = self.config.get("prefer_dual_audio", True)
        self.want_best = self.config.get("want_best", True)

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

        if anime_mappings is None:
            anime_mappings = self.get_anime_mappings()
        if anidb_mappings is None:
            anidb_mappings = self.get_anidb_mappings()
        self.anime_mappings = anime_mappings
        self.anidb_mappings = anidb_mappings

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
            al_id (str): AniList ID
        """

        sd_entry = None
        try:
            sd_entry = self.seadex.from_id(al_id)
        except EntryNotFoundError:
            pass

        return sd_entry

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
        if tvdb_id is not None:
            anilist_mappings.update(
                {
                    n: m
                    for n, m in self.anime_mappings.items()
                    if m.get("tvdb_id", None) == tvdb_id
                }
            )
        if tmdb_id is not None:
            anilist_mappings.update(
                {
                    n: m
                    for n, m in self.anime_mappings.items()
                    if m.get(f"tmdb_{tmdb_type}_id", None) == tmdb_id
                }
            )
        if imdb_id is not None:
            anilist_mappings.update(
                {
                    n: m
                    for n, m in self.anime_mappings.items()
                    if m.get("imdb_id", None) == imdb_id
                }
            )

        # Filter out anything without an AniList ID
        anilist_mappings = {
            n: m
            for n, m in anilist_mappings.items()
            if m.get("anilist_id", None) is not None
        }

        # Sort by AniList ID
        anilist_mappings = dict(
            sorted(anilist_mappings.items(), key=lambda item: item[1].get("anilist_id"))
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

        # Pull out release groups, URLs, and hashes from the final list we have
        # as a dictionary
        seadex_release_groups = {}
        for t in final_torrent_list:

            if t.release_group not in seadex_release_groups:
                seadex_release_groups[t.release_group] = {"url": {}}

            seadex_release_groups[t.release_group]["url"][t.url] = {
                "url": t.url,
                "tracker": t.tracker,
                "hash": t.infohash,
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
            field_dict = {
                "name": f"SeaDex recommendation: {srg}",
                "value": "\n".join(srg_item["url"]),
            }

            fields.append(field_dict)

        return fields, anilist_thumb

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

            for url in srg_item["url"]:
                item_hash = srg_item["url"][url]["hash"]
                tracker = srg_item["url"][url]["tracker"]

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
        torr_info = self.qbit.torrents_info()
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
        )
        if result != "Ok.":
            raise Exception("Failed to add torrent")

        return "torrent_added"

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
            al_id (str): Al ID
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

            self.logger.info(
                left_aligned_string(
                    f"{srg}:",
                    total_length=self.log_line_length,
                )
            )
            for url in srg_item["url"]:
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
