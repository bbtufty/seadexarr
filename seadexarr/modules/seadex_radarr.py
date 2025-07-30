import copy
import time

import requests
from arrapi import RadarrAPI
from seadex import EntryNotFoundError

from .anilist import get_anilist_title, get_anilist_thumb
from .discord import discord_push
from .log import centred_string, left_aligned_string
from .seadex_arr import SeaDexArr


class SeaDexRadarr(SeaDexArr):

    def __init__(self,
                 config="config.yml"
                 ):
        """Sync Radarr instance with SeaDex

        Args:
            config (str, optional): Path to config file.
                Defaults to "config.yml".
        """

        SeaDexArr.__init__(self,
                           arr="radarr",
                           config=config,
                           )

        # Set up Radarr
        self.radarr_url = self.config.get("radarr_url", None)
        if not self.radarr_url:
            raise ValueError(f"radarr_url needs to be defined in {config}")

        self.radarr_api_key = self.config.get("radarr_api_key", None)
        if not self.radarr_api_key:
            raise ValueError(f"radarr_api_key needs to be defined in {config}")

        self.radarr = RadarrAPI(url=self.radarr_url,
                                apikey=self.radarr_api_key,
                                )

    def run(self):
        """Run the SeaDex Radarr syncer"""

        # Get all the anime movies
        all_radarr_movies = self.get_all_radarr_movies()
        n_radarr = len(all_radarr_movies)

        self.logger.info(
            centred_string(self.log_line_sep * self.log_line_length,
                           total_length=self.log_line_length,
                           )
        )
        self.logger.info(
            centred_string(f"Starting SeaDex-Radarr for {n_radarr} movies",
                           total_length=self.log_line_length,
                           )
        )
        self.logger.info(
            centred_string(self.log_line_sep * self.log_line_length,
                           total_length=self.log_line_length,
                           )
        )

        # Now start looping over these movies
        for radarr_idx, radarr_movie in enumerate(all_radarr_movies):

            # Pull Radarr/TMDB info out
            tmdb_id = radarr_movie.tmdbId
            radarr_title = radarr_movie.title
            radarr_movie_id = radarr_movie.id

            self.logger.info(
                centred_string(self.log_line_sep * self.log_line_length,
                               total_length=self.log_line_length,
                               )
            )
            self.logger.info(
                centred_string(f"[{radarr_idx + 1}/{n_radarr}] Radarr: {radarr_title}",
                               total_length=self.log_line_length,
                               )
            )
            self.logger.info(
                centred_string("-" * self.log_line_length,
                               total_length=self.log_line_length,
                               )
            )

            # Get the mappings from the Radarr movies to AniList
            al_mappings = self.get_anilist_ids(tmdb_id=tmdb_id)

            if len(al_mappings) == 0:
                self.logger.warning(
                    centred_string(f"No AniList mappings found for {radarr_title}. Skipping",
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

                # Map the TMDB ID through to AniList
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

                radarr_release_group = self.get_radarr_release_group(radarr_movie_id=radarr_movie_id)

                self.logger.debug(
                    centred_string(f"Radarr: {radarr_release_group}",
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
                radarr_matches_seadex = False
                if radarr_release_group in seadex_dict.keys():
                    radarr_matches_seadex = True

                if not radarr_matches_seadex:

                    self.logger.info(
                        centred_string(f"Mismatch found between SeaDex recommendation and existing Radarr movie!",
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

                    # The first field should be the Radarr group. If it's empty, mention it's missing
                    radarr_release_group_discord = copy.deepcopy(radarr_release_group)
                    if radarr_release_group_discord is None:
                        radarr_release_group_discord = "None"

                    field_dict = {"name": "Radarr Release:",
                                  "value": radarr_release_group_discord,
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
                                arr_title=radarr_title,
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

    def get_all_radarr_movies(self):
        """Get all movies in Radarr that have an associated AniDB ID"""

        # Get a list of all movies
        radarr_movies = []

        all_tmdb_ids = [self.anime_mappings[x].get("tmdb_movie_id", None)
                        for x in self.anime_mappings
                        if "tmdb_movie_id" in self.anime_mappings[x].keys()
                        ]

        for m in self.radarr.all_movies():
            tmdb_id = m.tmdbId
            if tmdb_id in all_tmdb_ids:
                radarr_movies.append(m)

        radarr_movies.sort(key=lambda x: x.title)

        return radarr_movies

    def get_anilist_ids(self,
                        tmdb_id,
                        ):
        """Get a list of entries that match on TMDB ID

        Args:
            tmdb_id (int): TMDB ID
        """

        anilist_mappings = {
            n: m for n, m in self.anime_mappings.items()
            if m.get("tmdb_movie_id", None) == tmdb_id
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

    def get_radarr_release_group(self,
                                 radarr_movie_id,
                                 ):
        """Get the release group for a Radarr movie

        Args:
            radarr_movie_id (int): ID for movie in Radarr
        """

        # Get the movie file if it exists
        mov_req_url = (f"{self.radarr_url}/api/v3/moviefile?"
                       f"movieId={radarr_movie_id}&"
                       f"apikey={self.radarr_api_key}"
                       )
        mov_req = requests.get(mov_req_url)

        radarr_release_group = [r["releaseGroup"] for r in mov_req.json()]

        # If we have multiple options, throw up an error
        if len(radarr_release_group) > 1:
            raise ValueError(f"Multiple files found for movie {radarr_movie_id}")

        # If we have nothing, return None
        elif len(radarr_release_group) == 0:
            radarr_release_group = None

        # Otherwise, take the release group
        else:
            radarr_release_group = radarr_release_group[0]

        return radarr_release_group
