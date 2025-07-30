import copy
import json
import os
import shutil
from datetime import datetime
from urllib.request import urlretrieve
from xml.etree import ElementTree

import qbittorrentapi
from ruamel.yaml import YAML
from seadex import SeaDexEntry

from .log import setup_logger, centred_string, left_aligned_string
from .torrent import get_nyaa_url

ANIME_IDS_URL = "https://raw.githubusercontent.com/Kometa-Team/Anime-IDs/refs/heads/master/anime_ids.json"
ANIDB_MAPPINGS_URL = "https://raw.githubusercontent.com/Anime-Lists/anime-lists/refs/heads/master/anime-list-master.xml"

ALLOWED_ARRS = [
    "radarr",
    "sonarr",
]

class SeaDexArr:

    def __init__(self,
                 arr="sonarr",
                 config="config.yml",
                 ):
        """Base class for SeaDexArr instances

        Args:
            arr (str, optional): Which Arr is being run.
                Defaults to "sonarr".
            config (str, optional): Path to config file.
                Defaults to "config.yml".
        """

        # If we don't have a config file, copy the sample to the current
        # working directory
        f_path = copy.deepcopy(__file__)
        config_template_path = os.path.join(os.path.dirname(f_path), "config_sample.yml")
        if not os.path.exists(config):
            shutil.copy(config_template_path, config)
            raise FileNotFoundError(f"{config} not found. Copying template")

        with open(config, "r") as f:
            self.config = YAML().load(f)

        # Check the config has all the same keys as the sample, if not add 'em in
        self.verify_config(config_path=config,
                           config_template_path=config_template_path,
                           )

        # qBit
        self.qbit = None
        qbit_info = self.config.get("qbit_info", None)

        # Check we've got everything we need
        qbit_info_provided = all([qbit_info.get(key, None) is not None for key in qbit_info])
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
        log_level = self.config.get("log_level", "INFO")
        self.logger = setup_logger(log_level=log_level)

        # Instantiate the SeaDex API
        self.seadex = SeaDexEntry()

        # Set up cache for AL API calls
        self.al_cache = {}

        self.log_line_sep = "="
        self.log_line_length = 80

    def verify_config(self,
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

        anything_changed = False

        # Loop over keys in the config template, add any missing
        for key in config_template:
            if key not in self.config:
                self.config[key] = config_template[key]
                anything_changed = True

        # Loop over keys in the config file, remove any that aren't
        # in the template
        for key in self.config:
            if key not in config_template:
                del self.config[key]
                anything_changed = True

        # Save out if anything's changed
        if anything_changed:
            with open(config_path, "w+") as f:
                YAML().dump(self.config, f)

    def get_anime_mappings(self):
        """Get the anime IDs file"""

        anime_mappings_file = os.path.join("anime_ids.json")

        # If a file doesn't exist, get it
        self.get_external_mappings(f=anime_mappings_file,
                                   url=ANIME_IDS_URL,
                                   )

        with open(anime_mappings_file, "r") as f:
            anime_mappings = json.load(f)

        return anime_mappings

    def get_anidb_mappings(self):
        """Get the AniDB mappings file"""

        anidb_mappings_file = os.path.join("anime-list-master.xml")

        # If a file doesn't exist, get it
        self.get_external_mappings(f=anidb_mappings_file,
                                   url=ANIDB_MAPPINGS_URL,
                                   )

        anidb_mappings = ElementTree.parse(anidb_mappings_file).getroot()

        return anidb_mappings

    def get_external_mappings(self,
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

    def get_seadex_dict(self,
                        sd_entry,
                        ):
        """Parse and filter SeaDex request

        Args:
            sd_entry: SeaDex API query
        """

        # Start by potentially filtering down to only public ones
        if self.public_only:
            final_torrent_list = [t for t in sd_entry.torrents
                                  if t.tracker.is_public()
                                  ]
        else:
            final_torrent_list = copy.deepcopy(sd_entry.torrents)

        # Next, pull out ones tagged as best, so long as at least one
        # is tagged as best
        if self.want_best:
            any_best = any([t.is_best
                            for t in final_torrent_list
                            ])
            if any_best:
                final_torrent_list = [t for t in final_torrent_list
                                      if t.is_best
                                      ]

        # Now, if we prefer dual audio then remove any that aren't
        # tagged, so long as at least one is tagged
        if self.prefer_dual_audio:
            any_dual_audio = any([t.is_dual_audio
                                  for t in final_torrent_list
                                  ])
            if any_dual_audio:
                final_torrent_list = [t for t in final_torrent_list
                                      if t.is_dual_audio
                                      ]

        # Pull out release groups, URLs, and hashes from the final list we have
        # as a dictionary
        seadex_release_groups = {}
        for t in final_torrent_list:

            if t.release_group not in seadex_release_groups:
                seadex_release_groups[t.release_group] = {
                    "url": {}
                }

            seadex_release_groups[t.release_group]["url"][t.url] = {"url": t.url,
                                                                    "tracker": t.tracker.name,
                                                                    "hash": t.infohash,
                                                                    }
        return seadex_release_groups

    def add_torrent(self,
                    torrent_dict,
                    torrent_client="qbit",
                    ):
        """Add torrent(s) to a torrent client

        Args:
            torrent_dict (dict): Dictionary of torrent info
            torrent_client (str): Torrent client to use. Options are
                "qbit" for qBittorrent. Defaults to "qbit"
        """

        for srg, srg_item in torrent_dict.items():

            self.logger.info(
                left_aligned_string(f"Adding torrent(s) for group {srg} to {torrent_client}",
                                    total_length=self.log_line_length,
                                    )
            )

            for url in srg_item["url"]:
                item_hash = srg_item["url"][url]["hash"]
                tracker = srg_item["url"][url]["tracker"]

                # Nyaa
                if tracker.lower() == "nyaa":
                    parsed_url = get_nyaa_url(url)

                # Otherwise, bug out
                else:
                    raise ValueError(f"Unable to parse torrent links from {tracker}")

                if parsed_url is None:
                    raise Exception("Have not managed to parse the torrent URL")

                if torrent_client == "qbit":
                    success = self.add_torrent_to_qbit(url=url,
                                                       torrent_url=parsed_url,
                                                       torrent_hash=item_hash,
                                                       )

                else:
                    raise ValueError(f"Unsupported torrent client {torrent_client}")

                if success:
                    self.logger.info(
                        left_aligned_string(f"   Added {parsed_url} to {torrent_client}",
                                            total_length=self.log_line_length,
                                            )
                    )

                    # Increment the number of torrents added, and if we've hit the limit then
                    # jump out
                    self.torrents_added += 1
                    if self.max_torrents_to_add is not None:
                        if self.torrents_added >= self.max_torrents_to_add:
                            return True

                else:
                    raise ValueError(f"Cannot handle torrent client {torrent_client}")

        return True

    def add_torrent_to_qbit(self,
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
                centred_string(f"Torrent {url} already in qBittorrent",
                               total_length=self.log_line_length,
                               )
            )
            return True

        # Add the torrent
        result = self.qbit.torrents_add(urls=torrent_url,
                                        category=self.torrent_category,
                                        )
        if result != "Ok.":
            raise Exception("Failed to add torrent")

        return True