import copy
import json
import os
from datetime import datetime
from urllib.request import urlretrieve
from xml.etree import ElementTree

import qbittorrentapi
from seadex import SeaDexEntry

from .log import setup_logger, centred_string, left_aligned_string
from .torrent import get_nyaa_url

ANIME_IDS_URL = "https://raw.githubusercontent.com/Kometa-Team/Anime-IDs/refs/heads/master/anime_ids.json"
ANIDB_MAPPINGS_URL = "https://raw.githubusercontent.com/Anime-Lists/anime-lists/refs/heads/master/anime-list-master.xml"

class SeaDexArr:

    def __init__(self,
                 qbit_info=None,
                 torrent_category=None,
                 max_torrents_to_add=None,
                 discord_url=None,
                 public_only=True,
                 prefer_dual_audio=True,
                 want_best=True,
                 anime_mappings=None,
                 anidb_mappings=None,
                 sleep_time=2,
                 cache_time=1,
                 interactive=False,
                 log_level="INFO",
                 ):
        """Base class for SeaDexArr instances

        Args:
            qbit_info (dict): Dictionary of qBit info
            torrent_category (str): Torrent category for particular arr.
                Defaults to None
            public_only (bool): Whether to only return URLs for public torrents.
                Defaults to True
            prefer_dual_audio (bool): Whether to prefer dual audio torrents.
                Defaults to True
            want_best (bool): Whether to return only torrents marked as best.
                Defaults to True
            anime_mappings (dict): Custom mappings between TVDB/TMDB/AniList.
                Defaults to None, which will use the default mappings
                from Kometa (https://github.com/Kometa-Team/Anime-IDs)
            anidb_mappings (dict): Custom mappings between TVDB/TMDB/AniDB.
                Defaults to None, which will use the default mappings
                from https://github.com/Anime-Lists/anime-lists/
            sleep_time (float): Time to wait, in seconds, between requests, to avoid
                hitting API rate limits. Defaults to 0 seconds (no sleep).
            cache_time (float): Cache time for files that provide mappings.
                Defaults to 1 day
            interactive (bool): Whether to run in interactive mode.
            log_level (str): Logging level. Defaults to INFO.
        """

        self.cache_time = cache_time

        # Get the mapping files
        if anime_mappings is None:
            anime_mappings = self.get_anime_mappings()
        if anidb_mappings is None:
            anidb_mappings = self.get_anidb_mappings()

        self.anime_mappings = anime_mappings
        self.anidb_mappings = anidb_mappings

        # Instantiate the SeaDex API
        self.seadex = SeaDexEntry()

        # Set up torrent-related stuff

        # qBit
        self.qbit = None
        if qbit_info is not None:
            qbit = qbittorrentapi.Client(**qbit_info)

            # Ensure this works
            try:
                qbit.auth_log_in()
            except qbittorrentapi.LoginFailed:
                raise ValueError("qBittorrent login failed!")

            self.qbit = qbit

        # Hooks between torrents and Arrs, and torrent number
        # bookkeeping
        self.torrent_category = torrent_category
        self.max_torrents_to_add = max_torrents_to_add
        self.torrents_added = 0

        # Discord
        self.discord_url = discord_url

        # Set up cache for AL API calls
        self.al_cache = {}

        # Flags for filtering torrents
        self.public_only = public_only
        self.prefer_dual_audio = prefer_dual_audio
        self.want_best = want_best

        self.interactive = interactive

        self.sleep_time = sleep_time

        self.logger = setup_logger(log_level=log_level)

        self.log_line_sep = "="
        self.log_line_length = 80

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
            return False

        # Add the torrent
        result = self.qbit.torrents_add(urls=torrent_url,
                                        category=self.torrent_category,
                                        )
        if result != "Ok.":
            raise Exception("Failed to add torrent")

        return True