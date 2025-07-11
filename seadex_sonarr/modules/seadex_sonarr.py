import copy
import json
import os
import time
from datetime import datetime
from urllib.request import urlretrieve

import arrapi.exceptions
import requests
from arrapi import SonarrAPI
from seadex import SeaDexEntry, EntryNotFoundError

from .anilist import get_anilist_title, get_anilist_n_eps, get_anilist_thumb
from .discord import discord_push
from .log import setup_logger, centred_string, left_aligned_string

ANIME_IDS_URL = "https://raw.githubusercontent.com/Kometa-Team/Anime-IDs/refs/heads/master/anime_ids.json"


def get_tvdb_id(mapping):
    """Get TVDB ID for a particular mapping

    Args:
        mapping (dict): Dictionary of SeaDex mappings

    Returns:
        int: TVDB ID
    """

    tvdb_id = mapping.get("tvdb_id", None)

    return tvdb_id


def get_tvdb_season(mapping):
    """Get TVDB season for a particular mapping

    Args:
        mapping (dict): Dictionary of SeaDex mappings

    Returns:
        int: TVDB season
    """

    tvdb_season = mapping.get("tvdb_season", -1)

    return tvdb_season


class SeaDexSonarr:

    def __init__(self,
                 sonarr_url,
                 sonarr_api_key,
                 discord_url=None,
                 public_only=True,
                 prefer_dual_audio=True,
                 want_best=True,
                 anime_mappings=None,
                 sleep_time=0,
                 anime_id_cache_time=1,
                 log_level="INFO",
                 ):
        """Sync Sonarr instance with SeaDex

        Args:
            sonarr_url (str): URL for Sonarr instance
            sonarr_api_key (str): API key for Sonarr instance
            public_only (bool): Whether to only return URLs for public torrents.
                Defaults to True
            prefer_dual_audio (bool): Whether to prefer dual audio torrents.
                Defaults to True
            want_best (bool): Whether to return only torrents marked as best.
                Defaults to True
            anime_mappings (dict): Custom mappings between TVDB/AniList.
                Defaults to None, which will use the default mappings
                from Kometa (https://github.com/Kometa-Team/Anime-IDs)
            sleep_time (float): Time to wait, in seconds, between requests, to avoid
                hitting API rate limits. Defaults to 0 seconds (no sleep).
            anime_id_cache_time (float): Cache time for the Kometa anime ID file.
                Defaults to 1 day
            log_level (str): Logging level. Defaults to INFO.
        """

        self.anime_id_cache_time = anime_id_cache_time

        # Get the anime mappings file
        if anime_mappings is None:
            anime_mappings = self.get_anime_mappings()

        self.anime_mappings = anime_mappings

        # Instantiate the SeaDex API
        self.seadex = SeaDexEntry()

        # Set up Sonarr
        self.sonarr_url = sonarr_url
        self.sonarr_api_key = sonarr_api_key
        self.sonarr = SonarrAPI(url=self.sonarr_url,
                                apikey=self.sonarr_api_key,
                                )

        # Set up cache for AL API calls
        self.al_cache = {}

        # Discord
        self.discord_url = discord_url

        # Flags for filtering torrents
        self.public_only = public_only
        self.prefer_dual_audio = prefer_dual_audio
        self.want_best = want_best

        self.sleep_time = sleep_time

        self.logger = setup_logger(log_level=log_level)

        self.log_line_sep = "="
        self.log_line_length = 80

    def run(self):
        """Run the SeaDex Sonarr Syncer"""

        # Get all the anime series
        all_sonarr_series = self.get_all_sonarr_series()
        n_sonarr = len(all_sonarr_series)

        self.logger.info(
            centred_string(self.log_line_sep * self.log_line_length,
                           total_length=self.log_line_length,
                           )
        )
        self.logger.info(
            centred_string(f"Starting SeaDex-Sonarr for {n_sonarr} series",
                           total_length=self.log_line_length,
                           )
        )
        self.logger.info(
            centred_string(self.log_line_sep * self.log_line_length,
                           total_length=self.log_line_length,
                           )
        )

        # Now start looping over these series, finding any potential mappings
        for sonarr_idx, sonarr_series in enumerate(all_sonarr_series):

            # Pull Sonarr/TVDB info out
            tvdb_id = sonarr_series.tvdbId
            sonarr_title = sonarr_series.title
            sonarr_series_id = sonarr_series.id

            self.logger.info(
                centred_string(self.log_line_sep * self.log_line_length,
                               total_length=self.log_line_length,
                               )
            )
            self.logger.info(
                centred_string(f"[{sonarr_idx + 1}/{n_sonarr}] Sonarr: {sonarr_title}",
                               total_length=self.log_line_length,
                               )
            )
            self.logger.info(
                centred_string("-" * self.log_line_length,
                               total_length=self.log_line_length,
                               )
            )

            # Get the mappings from the Sonarr series to AniList
            al_mappings = self.get_anilist_ids(tvdb_id=tvdb_id)

            if len(al_mappings) == 0:
                self.logger.warning(
                    centred_string(f"No AniList mappings found for {sonarr_title}. Skipping",
                                   total_length=self.log_line_length,
                                   )
                )
                self.logger.info(
                    centred_string(self.log_line_sep * self.log_line_length,
                                   total_length=self.log_line_length,
                                   )
                )
                continue

            for mapping_idx, mapping in al_mappings.items():

                # Map the TVDB ID through to AniList
                al_id = mapping.get("anilist_id", None)
                if al_id is None:
                    self.logger.debug(
                        centred_string(f"-> No AL ID found. Continuing",
                                       total_length=self.log_line_length,
                                       )
                    )
                    self.logger.debug(
                        centred_string("-" * self.log_line_length,
                                       total_length=self.log_line_length,
                                       )
                    )
                    continue

                # Get the SeaDex entry, if it exists
                try:
                    sd_entry = self.seadex.from_id(al_id)
                except EntryNotFoundError:
                    self.logger.debug(
                        centred_string(f"No SeaDex entry found for AniList ID {al_id}. Continuing",
                                       total_length=self.log_line_length,
                                       )
                    )
                    self.logger.debug(
                        centred_string("-" * self.log_line_length,
                                       total_length=self.log_line_length,
                                       )
                    )
                    continue

                is_incomplete = sd_entry.is_incomplete

                # Get the AniList title
                anilist_title, self.al_cache = get_anilist_title(al_id,
                                                                 al_cache=self.al_cache,
                                                                 )

                # Get a string, marking if things are incomplete
                al_str = f"AniList: {anilist_title}"
                if is_incomplete:
                    al_str += f" [MARKED INCOMPLETE]"

                self.logger.info(
                    centred_string(al_str,
                                   total_length=self.log_line_length,
                                   )
                )

                # Get the episode list for all relevant episodes
                ep_list = self.get_ep_list(sonarr_series_id=sonarr_series_id,
                                           mapping=mapping,
                                           )

                sonarr_release_groups = self.get_sonarr_release_groups(ep_list=ep_list)

                self.logger.debug(
                    centred_string(f"Sonarr: {', '.join(sonarr_release_groups)}",
                                   total_length=self.log_line_length,
                                   )
                )

                # Produce a dictionary of info from the SeaDex request
                seadex_dict = self.get_seadex_dict(sd_entry=sd_entry)

                self.logger.debug(
                    centred_string(f"SeaDex: {', '.join(seadex_dict)}",
                                   total_length=self.log_line_length,
                                   )
                )

                # Check these things match up how we'd expect
                sonarr_matches_seadex = False
                for sonarr_release_group in sonarr_release_groups:
                    if sonarr_release_group in seadex_dict.keys():
                        sonarr_matches_seadex = True

                if not sonarr_matches_seadex:

                    self.logger.info(
                        centred_string(f"Mismatch found between SeaDex recommendation and existing files on Sonarr!",
                                       total_length=self.log_line_length,
                                       )
                    )
                    self.logger.info(
                        centred_string(f"SeaDex recommended version(s):",
                                       total_length=self.log_line_length,
                                       )
                    )

                    anilist_thumb, self.al_cache = get_anilist_thumb(al_id=al_id,
                                                                     al_cache=self.al_cache,
                                                                     )
                    fields = []

                    # First field should be the Sonarr groups. If it's empty, mention it's missing
                    sonarr_release_groups_discord = copy.deepcopy(sonarr_release_groups)
                    if len(sonarr_release_groups_discord) == 0:
                        sonarr_release_groups_discord = ["None"]

                    field_dict = {"name": "Sonarr",
                                  "value": "\n".join(sonarr_release_groups_discord),
                                  }
                    fields.append(field_dict)

                    # Then SeaDex options with links
                    for srg, srg_item in seadex_dict.items():

                        self.logger.info(
                            left_aligned_string(f"{srg}:",
                                                total_length=self.log_line_length,
                                                )
                        )
                        for url in srg_item["url"]:
                            self.logger.info(
                                left_aligned_string(f"   {url}",
                                                    total_length=self.log_line_length,
                                                    )
                            )

                        field_dict = {"name": srg,
                                      "value": "\n".join(srg_item["url"]),
                                      }

                        fields.append(field_dict)

                    if len(fields) > 0 and self.discord_url is not None:
                        discord_push(
                            url=self.discord_url,
                            sonarr_title=sonarr_title,
                            al_title=anilist_title,
                            fields=fields,
                            thumb_url=anilist_thumb,
                        )
                else:

                    self.logger.info(
                        centred_string(f"You already have the recommended release(s) for this title",
                                       total_length=self.log_line_length,
                                       )
                    )

                self.logger.info(
                    centred_string("-" * self.log_line_length,
                                   total_length=self.log_line_length,
                                   )
                )

                # Add in a wait, if required
                time.sleep(self.sleep_time)

            self.logger.info(
                centred_string(self.log_line_sep * self.log_line_length,
                               total_length=self.log_line_length,
                               )
            )

            # Add in a blank line to break things up
            self.logger.info("")

        return True

    def get_anime_mappings(self):
        """Get the anime IDs file"""

        anime_mappings_file = os.path.join("anime_ids.json")

        # If file doesn't exist, get it
        if not os.path.exists(anime_mappings_file):
            urlretrieve(ANIME_IDS_URL, anime_mappings_file)

        # Check if this is older than
        anime_mtime = os.path.getmtime(anime_mappings_file)
        anime_datetime = datetime.fromtimestamp(anime_mtime)
        now_datetime = datetime.now()

        # Get the time difference
        t_diff = now_datetime - anime_datetime

        # If the file is older than the cache time, re-download
        if t_diff.days >= self.anime_id_cache_time:
            urlretrieve(ANIME_IDS_URL, anime_mappings_file)

        with open(anime_mappings_file, "r") as f:
            anime_mappings = json.load(f)

        return anime_mappings

    def get_all_sonarr_series(self):
        """Get all series in Sonarr tagged as anime"""

        # Get a list of everything marked as type Anime in the Sonarr instance
        sonarr_series = []

        for s in self.sonarr.all_series():
            sonarr_series_type = s.seriesType

            if sonarr_series_type == "anime":
                sonarr_series.append(s)

        sonarr_series.sort(key=lambda x: x.title)

        return sonarr_series

    def get_sonarr_series(self, tvdb_id):
        """Get Sonarr series for a given TVDB ID

        Args:
            tvdb_id (int): TVDB ID
        """

        try:
            series = self.sonarr.get_series(tvdb_id=tvdb_id)
        except arrapi.exceptions.NotFound:
            series = None

        return series

    def get_anilist_ids(self,
                        tvdb_id,
                        ):
        """Get list of entries that match on TVDB ID

        Args:
            tvdb_id (int): TVDB ID
        """

        anilist_mappings = {
            n: m for n, m in self.anime_mappings.items()
            if m.get("tvdb_id", None) == tvdb_id
        }

        # Filter out anything without an AniList ID
        anilist_mappings = {
            n: m for n, m in anilist_mappings.items()
            if m.get("anilist_id", None) is not None
        }

        # Sort by AniList ID
        anilist_mappings = dict(sorted(anilist_mappings.items(),
                                       key=lambda item: item[1].get("anilist_id")
                                       )
                                )

        return anilist_mappings

    def get_ep_list(self,
                    sonarr_series_id,
                    mapping,
                    ):
        """Get list of relevant episodes for an AniList mapping

        Args:
            sonarr_series_id (int): Series ID in Sonarr
            mapping (dict): Mappings between TVDB and AniList
        """

        # If we have any season info, pull that out now
        tvdb_season = get_tvdb_season(mapping)
        al_id = mapping.get("anilist_id", -1)

        if al_id == -1:
            raise ValueError("AniList ID not defined!")

        # Get all the episodes for a season. Use the raw Sonarr API
        # call here to get details
        eps_req_url = (f"{self.sonarr_url}/api/v3/episode?"
                       f"seriesId={sonarr_series_id}&"
                       f"includeImages=false&"
                       f"includeEpisodeFile=true&"
                       f"apikey={self.sonarr_api_key}"
                       )
        eps_req = requests.get(eps_req_url)

        if eps_req.status_code != 200:
            raise Warning("Failed get episodes data from Sonarr")

        ep_list = eps_req.json()

        # Sort by season/episode number for slicing later
        ep_list = sorted(ep_list, key=lambda x: (x["seasonNumber"], x["episodeNumber"]))

        # Filter down here by various things
        final_ep_list = []
        for ep in ep_list:

            include_episode = True

            # First, check by season

            # If the TVDB season is -1, this is anything but specials
            if tvdb_season == -1 and ep["seasonNumber"] == 0:
                include_episode = False

            # Else, if we have a season defined, and it doesn't match, don't include
            elif tvdb_season != -1 and ep["seasonNumber"] != tvdb_season:
                include_episode = False

            # If we've passed the vibe check, include things now
            if include_episode:
                final_ep_list.append(ep)

        # Slice the list to get the correct episodes, so any potential offsets
        ep_offset = mapping.get("tvdb_epoffset", 0)
        n_eps, self.al_cache = get_anilist_n_eps(al_id,
                                                 al_cache=self.al_cache,
                                                 )

        # If we don't get a number of episodes, use them all
        if n_eps is None:
            n_eps = len(final_ep_list) - ep_offset

        final_ep_list = final_ep_list[ep_offset:n_eps + ep_offset]

        return final_ep_list

    def get_sonarr_release_groups(self,
                                  ep_list,
                                  ):
        """Get a unique list of release groups for a series in Sonarr

        Args:
            ep_list (list): List of episodes
        """

        # Look through, get release groups from the existing Sonarr files
        # and note any potential missing files
        sonarr_release_groups = []
        missing_eps = 0
        n_eps = len(ep_list)
        for ep in ep_list:

            # Get missing episodes, then skip
            if ep["episodeFileId"] == 0:
                missing_eps += 1
                continue

            release_group = ep.get("episodeFile", {}).get("releaseGroup", None)
            if release_group is None:
                continue

            if release_group not in sonarr_release_groups:
                sonarr_release_groups.append(release_group)

        if missing_eps > 0:
            self.logger.info(
                centred_string(f"Missing episodes: {missing_eps}/{n_eps}",
                               total_length=self.log_line_length,
                               )
            )

        sonarr_release_groups.sort()

        return sonarr_release_groups

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

        # Pull out release groups and URLs from the final list we have
        # as a dictionary
        seadex_release_groups = {}
        for t in final_torrent_list:

            if t.release_group not in seadex_release_groups:
                seadex_release_groups[t.release_group] = {
                    "url": []
                }
            seadex_release_groups[t.release_group]["url"].append(t.url)

        return seadex_release_groups
