import copy
import time
import os
from urllib.parse import urlencode

import arrapi.exceptions
import requests
from arrapi import SonarrAPI

from .anilist import (
    get_anilist_n_eps,
    get_anilist_format,
)
from .discord import discord_push
from .log import centred_string, left_aligned_string
from .seadex_arr import SeaDexArr
from .seadex_radarr import SeaDexRadarr


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


def get_overlapping_results(seadex_dict):
    """See if SeaDex releases have overlapping episodes

    Args:
        seadex_dict (dict): Dictionary of SeaDex releases
    """

    overlapping_results = False
    if len(seadex_dict) > 0:
        for rg1 in seadex_dict:

            rg1_all_eps = seadex_dict.get(rg1, {}).get("all_episodes", [])

            for rg2 in seadex_dict:

                if rg1 == rg2:
                    continue

                rg2_all_eps = seadex_dict.get(rg1, {}).get("all_episodes", [])

                if len(rg2_all_eps) == 0 or len(rg2_all_eps) == 0:
                    overlapping_results = True

                # Also, if we have an instance where one hasn't been parsed
                # but the other has, then just assume they overlap

                intersect = list(
                    filter(
                        lambda x: x in rg1_all_eps,
                        rg2_all_eps,
                    )
                )
                if len(intersect) > 0:
                    overlapping_results = True

    return overlapping_results


class SeaDexSonarr(SeaDexArr):

    def __init__(
        self,
        config="config.yml",
        cache="cache.json",
        logger=None,
    ):
        """Sync Sonarr instance with SeaDex

        Args:
            config (str, optional): Path to config file.
                Defaults to "config.yml".
            cache (str, optional): Path to cache file.
                Defaults to "cache.json".
            logger. Logging instance. Defaults to None,
                which will create one.
        """

        SeaDexArr.__init__(
            self,
            arr="sonarr",
            config=config,
            cache=cache,
            logger=logger,
        )

        # Set up Sonarr
        self.sonarr_url = self.config.get("sonarr_url", None)
        if not self.sonarr_url:
            raise ValueError(f"sonarr_url needs to be defined in {config}")

        self.sonarr_api_key = self.config.get("sonarr_api_key", None)
        if not self.sonarr_api_key:
            raise ValueError(f"sonarr_api_key needs to be defined in {config}")

        self.sonarr = SonarrAPI(
            url=self.sonarr_url,
            apikey=self.sonarr_api_key,
        )

        self.ignore_movies_in_radarr = self.config.get("ignore_movies_in_radarr", False)

        # Also, if we have Radarr info, set up an instance there
        self.radarr = None
        self.all_radarr_movies = None
        radarr_url = self.config.get("radarr_url", None)
        radarr_api_key = self.config.get("radarr_api_key", None)

        if radarr_url is not None and radarr_api_key is not None:
            self.radarr = SeaDexRadarr(
                config=config,
                logger=logger,
            )
            self.all_radarr_movies = self.radarr.get_all_radarr_movies()

    def run(self):
        """Run the SeaDex Sonarr Syncer"""

        # Get all the anime series
        all_sonarr_series = self.get_all_sonarr_series()
        n_sonarr = len(all_sonarr_series)

        self.log_arr_start(
            arr="sonarr",
            n_items=n_sonarr,
        )

        # Now start looping over these series, finding any potential mappings
        for sonarr_idx, sonarr_series in enumerate(all_sonarr_series):

            # Pull Sonarr and database info out
            tvdb_id = sonarr_series.tvdbId
            imdb_id = sonarr_series.imdbId
            sonarr_title = sonarr_series.title
            sonarr_series_id = sonarr_series.id

            self.log_arr_item_start(
                arr="sonarr",
                item_title=sonarr_title,
                n_item=sonarr_idx + 1,
                n_items=n_sonarr,
            )

            # If we're not monitored, then skip if ignore_unmonitored is switched on
            if not sonarr_series.monitored and self.ignore_unmonitored:
                self.log_arr_item_unmonitored(
                    arr="sonarr",
                    item_title=sonarr_title,
                )
                continue

            # Get the mappings from the Sonarr series to AniList
            al_mappings = self.get_anilist_ids(
                tvdb_id=tvdb_id,
                imdb_id=imdb_id,
            )

            if len(al_mappings) == 0:
                self.log_no_anilist_mappings(title=sonarr_title)
                continue

            for anidb_id, mapping in al_mappings.items():

                # Map the TVDB ID through to AniList
                al_id = mapping.get("anilist_id", None)
                if al_id is None:
                    self.log_no_anilist_id()
                    continue

                # Get the SeaDex entry if it exists
                sd_entry = self.get_seadex_entry(al_id=al_id)
                if sd_entry is None:
                    self.log_no_sd_entry(al_id=al_id)
                    continue
                sd_url = sd_entry.url

                # Check if we've already got this cached
                al_id_in_cache = self.check_al_id_in_cache(
                    arr="sonarr",
                    al_id=al_id,
                    seadex_entry=sd_entry,
                )

                if al_id_in_cache:
                    self.logger.info(
                        centred_string(
                            f"Cache time for AniList ID {al_id} matches SeaDex updated time",
                            total_length=self.log_line_length,
                        )
                    )
                    self.logger.info(
                        centred_string(
                            "-" * self.log_line_length,
                            total_length=self.log_line_length,
                        )
                    )
                    continue

                # Also check if it's in the Radarr cache, if we have that option
                if self.ignore_movies_in_radarr:
                    al_id_in_radarr_cache = self.check_al_id_in_cache(
                        arr="radarr",
                        al_id=al_id,
                        seadex_entry=sd_entry,
                    )
                    if al_id_in_radarr_cache:
                        self.logger.info(
                            centred_string(
                                f"Found AniList ID {al_id} in Radarr cache, "
                                f"and cache time matches SeaDex updated time",
                                total_length=self.log_line_length,
                            )
                        )
                        self.logger.info(
                            centred_string(
                                "-" * self.log_line_length,
                                total_length=self.log_line_length,
                            )
                        )
                        continue

                # Get the AniList title
                anilist_title = self.get_anilist_title(
                    al_id=al_id,
                    sd_entry=sd_entry,
                )

                # If we have a Radarr instance, and we don't want to add movies that
                # are already in Radarr, do that now
                if (
                    self.radarr is not None
                    and self.all_radarr_movies is not None
                    and self.ignore_movies_in_radarr
                ):

                    radarr_movies = []

                    # Make sure these are flagged as specials since
                    # sometimes shows and movies are all lumped together
                    mapping_season = mapping.get("tvdb_season", -1)
                    if mapping_season == 0:

                        mapping_tmdb_id = mapping.get("tmdb_movie_id", None)
                        mapping_imdb_id = mapping.get("imdb_id", None)

                        for m in self.all_radarr_movies:

                            # Check by TMDB IDs
                            if mapping_tmdb_id is not None:
                                if (
                                    m.tmdbId == mapping_tmdb_id
                                    and m not in radarr_movies
                                ):
                                    radarr_movies.append(m)

                            # Check by IMDb IDs
                            if mapping_imdb_id is not None:
                                if (
                                    m.imdbId == mapping_imdb_id
                                    and m not in radarr_movies
                                ):
                                    radarr_movies.append(m)

                    if len(radarr_movies) > 0:

                        for movie in radarr_movies:
                            self.logger.info(
                                centred_string(
                                    f"{movie.title} found in Radarr, will skip",
                                    total_length=self.log_line_length,
                                )
                            )

                        self.logger.info(
                            centred_string(
                                "-" * self.log_line_length,
                                total_length=self.log_line_length,
                            )
                        )

                        time.sleep(self.sleep_time)
                        continue

                # Get the episode list for all relevant episodes
                ep_list = self.get_ep_list(
                    sonarr_series_id=sonarr_series_id,
                    anidb_id=anidb_id,
                    mapping=mapping,
                )

                # If all episodes are unmonitored, then skip if ignore_unmonitored is switched on
                ep_list_monitored = [x.get("monitored", True) for x in ep_list]
                if not any(ep_list_monitored) and self.ignore_unmonitored:
                    self.log_anilist_item_unmonitored(
                        arr="sonarr",
                        item_title=anilist_title,
                    )
                    time.sleep(self.sleep_time)
                    continue

                sonarr_release_groups = self.get_sonarr_release_groups(ep_list=ep_list)

                self.logger.debug(
                    centred_string(
                        f"Sonarr: {', '.join(sonarr_release_groups)}",
                        total_length=self.log_line_length,
                    )
                )

                # Produce a dictionary of info from the SeaDex request
                seadex_dict = self.get_seadex_dict(sd_entry=sd_entry)

                if len(seadex_dict) == 0:
                    self.log_no_seadex_releases()
                    time.sleep(self.sleep_time)
                    continue

                self.logger.debug(
                    centred_string(
                        f"SeaDex: {', '.join(seadex_dict)}",
                        total_length=self.log_line_length,
                    )
                )

                # Parse out filenames and check for overlaps
                seadex_dict = self.parse_episodes_from_seadex(seadex_dict=seadex_dict)
                overlapping_results = get_overlapping_results(seadex_dict=seadex_dict)

                # If we're in interactive mode and there are multiple equivalent options here, then select
                if self.interactive and len(seadex_dict) > 1 and overlapping_results:
                    seadex_dict = self.filter_seadex_interactive(
                        seadex_dict=seadex_dict,
                        sd_entry=sd_entry,
                    )

                # Filter downloads by whether the episodes in each torrent match the release
                # group we have in Sonarr
                seadex_dict = self.filter_seadex_downloads(
                    seadex_dict=seadex_dict,
                    arr="sonarr",
                    arr_release_groups=sonarr_release_groups,
                    ep_list=ep_list,
                )

                any_to_download = self.get_any_to_download(seadex_dict=seadex_dict)

                if any_to_download:
                    self.log_arr_seadex_mismatch(
                        arr="sonarr",
                        seadex_dict=seadex_dict,
                    )
                    fields, anilist_thumb = self.get_seadex_fields(
                        arr="sonarr",
                        al_id=al_id,
                        release_group=sonarr_release_groups,
                        seadex_dict=seadex_dict,
                    )

                    # If we've got stuff, time to do something!
                    if len(seadex_dict) > 0:

                        # Keep track of how many torrents we've added
                        n_torrents_added = 0

                        # Add torrents to qBittorrent
                        if self.qbit is not None:
                            n_torrents_added += self.add_torrent(
                                torrent_dict=seadex_dict,
                                torrent_client="qbit",
                            )

                        # Otherwise, increment by the number of torrents in the SeaDex dict
                        else:
                            n_torrents_added += len(seadex_dict)
                            self.torrents_added += len(seadex_dict)

                        # Push a message to Discord if we've added anything
                        if self.discord_url is not None and n_torrents_added > 0:
                            discord_push(
                                url=self.discord_url,
                                arr_title=sonarr_title,
                                al_title=anilist_title,
                                seadex_url=sd_url,
                                fields=fields,
                                thumb_url=anilist_thumb,
                            )

                        if self.max_torrents_to_add is not None:
                            if self.torrents_added >= self.max_torrents_to_add:
                                self.log_max_torrents_added()
                                return True

                else:

                    self.logger.info(
                        centred_string(
                            f"You already have the recommended release(s) for this title",
                            total_length=self.log_line_length,
                        )
                    )

                # Update and save out the cache
                cache_details = {
                    "name": anilist_title,
                    "updated_at": sd_entry.updated_at,
                }

                self.update_cache(
                    arr="sonarr",
                    al_id=al_id,
                    cache_details=cache_details,
                )

                self.logger.info(
                    centred_string(
                        "-" * self.log_line_length,
                        total_length=self.log_line_length,
                    )
                )

                # Add in a wait, if required
                time.sleep(self.sleep_time)

            self.logger.info(
                centred_string(
                    self.log_line_sep * self.log_line_length,
                    total_length=self.log_line_length,
                )
            )

            if self.max_torrents_to_add is not None:
                if self.torrents_added >= self.max_torrents_to_add:
                    self.log_max_torrents_added()
                    return True

            # Add in a blank line to break things up
            self.logger.info("")

        return True

    def get_all_sonarr_series(self):
        """Get all series in Sonarr with AniList mapping info"""

        sonarr_series = []

        # Search through TVDB and IMDb IDs
        all_tvdb_ids = [
            self.anime_mappings[x].get("tvdb_id", None)
            for x in self.anime_mappings
            if "tvdb_id" in self.anime_mappings[x].keys()
        ]

        all_imdb_ids = [
            self.anime_mappings[x].get("imdb_id", None)
            for x in self.anime_mappings
            if "imdb_id" in self.anime_mappings[x].keys()
        ]

        for s in self.sonarr.all_series():

            # Check by TVDB IDs
            tvdb_id = s.tvdbId
            if tvdb_id in all_tvdb_ids and s not in sonarr_series:
                sonarr_series.append(s)

            # Check by IMDb IDs
            imdb_id = s.imdbId
            if imdb_id in all_imdb_ids and s not in sonarr_series:
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

    def get_ep_list(
        self,
        sonarr_series_id,
        anidb_id,
        mapping,
    ):
        """Get a list of relevant episodes for an AniList mapping

        Args:
            sonarr_series_id (int): Series ID in Sonarr
            anidb_id (int): AniDB ID
            mapping (dict): Mapping dictionary between TVDB and AniList
        """

        # If we have any season info, pull that out now
        tvdb_season = get_tvdb_season(mapping)
        al_id = mapping.get("anilist_id", -1)

        if al_id == -1:
            raise ValueError("AniList ID not defined!")

        # Get all the episodes for a season. Use the raw Sonarr API
        # call here to get details
        eps_req_url = (
            f"{self.sonarr_url}/api/v3/episode?"
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
        ep_list = sorted(
            ep_list,
            key=lambda x: (x.get("seasonNumber", None), x.get("episodeNumber", None)),
        )

        # Filter down here by various things
        final_ep_list = []
        for ep in ep_list:

            include_episode = True

            # First, check by season
            season_number = ep.get("seasonNumber", None)

            # If the TVDB season is -1, this is anything but specials
            if tvdb_season == -1 and season_number == 0:
                include_episode = False

            # Else, if we have a season defined, and it doesn't match, don't include
            elif tvdb_season != -1 and season_number != tvdb_season:
                include_episode = False

            # If we've passed the vibe check, include things now
            if include_episode:
                final_ep_list.append(ep)

        # For OVAs and movies, the offsets can often be wrong, so if we have specific mappings
        # then take that into account here
        al_format, self.al_cache = get_anilist_format(
            al_id,
            al_cache=self.al_cache,
        )

        # Potentially pull out a bunch of mappings from AniDB. These should
        # be for anything not marked as TV, and specials as marked by
        # being in Season 0
        anidb_mapping_dict = {}
        if al_format not in ["TV"] or tvdb_season == 0:
            anidb_item = self.anidb_mappings.findall(f"anime[@anidbid='{anidb_id}']")

            # If we don't find anything, no worries. If we find multiple, worries
            if len(anidb_item) > 1:
                raise ValueError(
                    "Multiple AniDB mappings found. This should not happen!"
                )

            if len(anidb_item) == 1:
                anidb_item = anidb_item[0]

                # We want things with mapping lists in, since more regular
                # mappings will have already been picked up
                anidb_mapping_list = anidb_item.findall("mapping-list")

                if len(anidb_mapping_list) > 0:
                    for ms in anidb_mapping_list:
                        m = ms.findall("mapping")
                        for i in m:

                            # If there's no text, continue
                            if not i.text:
                                continue

                            # Split at semicolons
                            i_split = i.text.strip(";").split(";")
                            i_split = [x.split("-") for x in i_split]

                            # Only match things if AniList and AniDB agree on the TVDB season
                            anidb_tvdbseason = int(i.attrib["tvdbseason"])
                            if not anidb_tvdbseason == tvdb_season:
                                continue

                            anidb_mapping_dict[anidb_tvdbseason] = {
                                int(x[1]): int(x[0]) for x in i_split
                            }

        # Prefer the AniDB mapping dict over any offsets
        if len(anidb_mapping_dict) > 0:
            anidb_final_ep_list = []

            # See if we have the mapping for each entry
            for ep in final_ep_list:

                season_number = ep.get("seasonNumber", None)
                episode_number = ep.get("episodeNumber", None)

                anidb_mapping_dict_entry = anidb_mapping_dict.get(
                    season_number, {}
                ).get(episode_number, None)
                if anidb_mapping_dict_entry is not None:
                    anidb_final_ep_list.append(ep)

            final_ep_list = copy.deepcopy(anidb_final_ep_list)

        else:

            # Slice the list to get the correct episodes, so any potential offsets
            ep_offset = mapping.get("tvdb_epoffset", 0)
            n_eps, self.al_cache = get_anilist_n_eps(
                al_id,
                al_cache=self.al_cache,
            )

            # If we don't get a number of episodes, use them all
            if n_eps is None:
                n_eps = len(final_ep_list) - ep_offset

            # Check that we're including this by the episode number. This only
            # works for single-seasons, so be careful!
            if tvdb_season != -1:
                final_ep_list = [
                    ep
                    for ep in final_ep_list
                    if 1 <= ep.get("episodeNumber", None) - ep_offset <= n_eps
                ]
            else:
                final_ep_list = final_ep_list[ep_offset: n_eps + ep_offset]

        return final_ep_list

    def get_sonarr_release_groups(
        self,
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
            if ep.get("episodeFileId", 0) == 0:
                missing_eps += 1
                continue

            release_group = ep.get("episodeFile", {}).get("releaseGroup", None)
            if release_group is None or release_group == "":
                continue

            if release_group not in sonarr_release_groups:
                sonarr_release_groups.append(release_group)

        if missing_eps > 0:
            self.logger.info(
                centred_string(
                    f"Missing episodes: {missing_eps}/{n_eps}",
                    total_length=self.log_line_length,
                )
            )

        sonarr_release_groups.sort()

        return sonarr_release_groups

    def parse_episodes_from_seadex(
        self,
        seadex_dict,
    ):
        """For files in a SeaDex release, parse this through Sonarr to get season/episode numbers

        This gets an overall episode list per-release group, and also episode lists per-torrent,
        if there are multiple

        Args:
            seadex_dict (dict): Dictionary of seadex releases
        """

        for release_group, release_group_item in seadex_dict.items():

            # Set up an overall "all episodes" list
            release_group_item.update({"all_episodes": []})

            for url, url_item in release_group_item.get("urls", {}).items():

                # Set up a list to parse episodes from files
                url_item.update({"episodes": []})

                for seadex_file in url_item.get("files", []):

                    # Get basename from the file, and encode it through for the API
                    # query
                    f = os.path.basename(seadex_file)

                    d = {"title": f, "apikey": self.sonarr_api_key}
                    d_enc = urlencode(d)

                    # Parse through Sonarr
                    parse_req_url = f"{self.sonarr_url}/api/v3/parse?" f"{d_enc}"
                    parse_req = requests.get(parse_req_url)
                    j = parse_req.json()

                    episode_info = j.get("episodes", [])

                    if len(episode_info) == 0:
                        self.logger.debug(
                            left_aligned_string(
                                f"Sonarr could not parse episode for {f}"
                            )
                        )
                        continue

                    # Add the season and episode numbers in
                    for ep in episode_info:

                        season = ep.get("seasonNumber", None)
                        episode = ep.get("episodeNumber", None)

                        if season is None or episode is None:
                            raise ValueError("Season or episode has come up None")

                        self.logger.debug(
                            left_aligned_string(
                                f"{f} mapped to: S{season:02d}E{episode:02d}"
                            )
                        )

                        url_item["episodes"].append(
                            {"season": season, "episode": episode}
                        )
                        release_group_item["all_episodes"].append(
                            {"season": season, "episode": episode}
                        )

        return seadex_dict
