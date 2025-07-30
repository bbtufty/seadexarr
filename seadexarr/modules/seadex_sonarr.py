import copy
import time

import arrapi.exceptions
import requests
from arrapi import SonarrAPI
from seadex import EntryNotFoundError

from .anilist import get_anilist_title, get_anilist_n_eps, get_anilist_thumb, get_anilist_format
from .discord import discord_push
from .log import centred_string, left_aligned_string
from .seadex_arr import SeaDexArr


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


class SeaDexSonarr(SeaDexArr):

    def __init__(self,
                 config="config.yml"
                 ):
        """Sync Sonarr instance with SeaDex

        Args:
            config (str, optional): Path to config file.
                Defaults to "config.yml".
        """

        SeaDexArr.__init__(self,
                           arr="sonarr",
                           config=config,
                           )

        # Set up Sonarr
        self.sonarr_url = self.config.get("sonarr_url", None)
        if not self.sonarr_url:
            raise ValueError(f"sonarr_url needs to be defined in {config}")

        self.sonarr_api_key = self.config.get("sonarr_api_key", None)
        if not self.sonarr_api_key:
            raise ValueError(f"sonarr_api_key needs to be defined in {config}")

        self.sonarr = SonarrAPI(url=self.sonarr_url,
                                apikey=self.sonarr_api_key,
                                )

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

            for anidb_id, mapping in al_mappings.items():

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

                # Get the SeaDex entry if it exists
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

                sd_url = sd_entry.url
                is_incomplete = sd_entry.is_incomplete

                # Get the AniList title
                anilist_title, self.al_cache = get_anilist_title(al_id,
                                                                 al_cache=self.al_cache,
                                                                 )

                # Get a string, marking if things are incomplete
                al_str = f"AniList: {anilist_title} ({sd_url})"
                if is_incomplete:
                    al_str += f" [MARKED INCOMPLETE]"

                self.logger.info(
                    centred_string(al_str,
                                   total_length=self.log_line_length,
                                   )
                )

                # Get the episode list for all relevant episodes
                ep_list = self.get_ep_list(sonarr_series_id=sonarr_series_id,
                                           anidb_id=anidb_id,
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

                if len(seadex_dict) == 0:
                    self.logger.info(
                        centred_string(f"No suitable releases found on SeaDex",
                                       total_length=self.log_line_length,
                                       )
                    )
                    self.logger.info(
                        centred_string("-" * self.log_line_length,
                                       total_length=self.log_line_length,
                                       )
                    )
                    continue

                self.logger.debug(
                    centred_string(f"SeaDex: {', '.join(seadex_dict)}",
                                   total_length=self.log_line_length,
                                   )
                )

                # If we're in interactive mode and there are multiple options here, then select
                if self.interactive and len(seadex_dict) > 1:

                    self.logger.warning(
                        centred_string(f"Multiple releases found!:",
                                       total_length=self.log_line_length,
                                       )
                    )
                    self.logger.warning(
                        left_aligned_string(f"Here are the SeaDex notes:",
                                            total_length=self.log_line_length,
                                            )
                    )

                    notes = sd_entry.notes.split("\n")
                    for n in notes:
                        self.logger.warning(
                            left_aligned_string(n,
                                                total_length=self.log_line_length,
                                                )
                        )
                    self.logger.warning(
                        left_aligned_string("",
                                            total_length=self.log_line_length,
                                            )
                    )

                    all_srgs = list(seadex_dict.keys())
                    for s_i, s in enumerate(all_srgs):
                        self.logger.warning(
                            left_aligned_string(f"[{s_i}]: {s}",
                                                total_length=self.log_line_length,
                                                )
                        )

                    srgs_to_grab = input(f"Which release do you want to grab? "
                                         f"Single number for one, comma separated list for multiple, or blank for all: ")

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
                                    left_aligned_string(f"Index {srg_idx} is out of range",
                                                        total_length=self.log_line_length,
                                                        )
                                )
                                continue
                            seadex_dict_filtered[srg] = copy.deepcopy(seadex_dict[srg])

                        seadex_dict = copy.deepcopy(seadex_dict_filtered)

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

                    # The first field should be the Sonarr groups. If it's empty, mention it's missing
                    sonarr_release_groups_discord = copy.deepcopy(sonarr_release_groups)
                    if len(sonarr_release_groups_discord) == 0:
                        sonarr_release_groups_discord = ["None"]

                    field_dict = {"name": "Sonarr Release(s):",
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

                        field_dict = {"name": f"SeaDex recommendation: {srg}",
                                      "value": "\n".join(srg_item["url"]),
                                      }

                        fields.append(field_dict)

                    # If we've got stuff, time to do something!
                    if len(fields) > 0:

                        # Add torrents to qBittorrent
                        if self.qbit is not None:
                            self.add_torrent(torrent_dict=seadex_dict,
                                             torrent_client="qbit",
                                             )

                        # Push a message to Discord
                        if self.discord_url is not None:
                            discord_push(
                                url=self.discord_url,
                                arr_title=sonarr_title,
                                al_title=anilist_title,
                                seadex_url=sd_url,
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

            if self.max_torrents_to_add is not None:
                if self.torrents_added >= self.max_torrents_to_add:
                    self.logger.info(
                        centred_string("Added maximum number of torrents for this run. Stopping",
                                       total_length=self.log_line_length,
                                       )
                    )
                    self.logger.info(
                        centred_string(self.log_line_sep * self.log_line_length,
                                       total_length=self.log_line_length,
                                       )
                    )
                    return True

            # Add in a blank line to break things up
            self.logger.info("")

        return True

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
        """Get a list of entries that match on TVDB ID

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

        # For OVAs and movies, the offsets can often be wrong, so if we have specific mappings
        # then take that into account here
        al_format, self.al_cache = get_anilist_format(al_id,
                                                      al_cache=self.al_cache,
                                                      )

        # Slice the list to get the correct episodes, so any potential offsets
        ep_offset = mapping.get("tvdb_epoffset", 0)
        n_eps, self.al_cache = get_anilist_n_eps(al_id,
                                                 al_cache=self.al_cache,
                                                 )

        # Potentially pull out a bunch of mappings from AniDB. These should
        # be for anything not marked as TV
        anidb_mapping_dict = {}
        if al_format not in ["TV"]:
            anidb_item = self.anidb_mappings.findall(f"anime[@anidbid='{anidb_id}']")

            # If we don't find anything, no worries. If we find multiple, worries
            if len(anidb_item) > 1:
                raise ValueError("Multiple AniDB mappings found. This should not happen!")

            if len(anidb_item) == 1:
                anidb_item = anidb_item[0]
                anidb_mapping_list = anidb_item.findall("mapping-list")
                if len(anidb_mapping_list) > 0:
                    for ms in anidb_mapping_list:
                        m = ms.findall("mapping")
                        for i in m:
                            # Split at semicolons
                            i_split = i.text.strip(";").split(";")
                            i_split = [x.split("-") for x in i_split]

                            # Only match things if AniList and AniDB agree on the TVDB season
                            anidb_tvdbseason = int(i.attrib["tvdbseason"])
                            if not anidb_tvdbseason == tvdb_season:
                                continue

                            anidb_mapping_dict[anidb_tvdbseason] = {int(x[1]): int(x[0]) for x in i_split}

        # Prefer the AniDB mapping dict over any offsets
        if len(anidb_mapping_dict) > 0:
            anidb_final_ep_list = []

            # See if we have the mapping for each entry
            for ep in final_ep_list:
                anidb_mapping_dict_entry = anidb_mapping_dict.get(ep["seasonNumber"], {}).get(ep["episodeNumber"], None)
                if anidb_mapping_dict_entry is not None:
                    anidb_final_ep_list.append(ep)

            final_ep_list = copy.deepcopy(anidb_final_ep_list)

        else:
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
