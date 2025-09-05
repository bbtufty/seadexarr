import time

import requests
import arrapi.exceptions
from arrapi import RadarrAPI

from .discord import discord_push
from .log import centred_string
from .seadex_arr import SeaDexArr


class SeaDexRadarr(SeaDexArr):

    def __init__(
        self,
        config="config.yml",
        cache="cache.json",
        logger=None,
    ):
        """Sync Radarr instance with SeaDex

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
            arr="radarr",
            config=config,
            cache=cache,
            logger=logger,
        )

        # Set up Radarr
        self.radarr_url = self.config.get("radarr_url", None)
        if not self.radarr_url:
            raise ValueError(f"radarr_url needs to be defined in {config}")

        self.radarr_api_key = self.config.get("radarr_api_key", None)
        if not self.radarr_api_key:
            raise ValueError(f"radarr_api_key needs to be defined in {config}")

        self.radarr = RadarrAPI(
            url=self.radarr_url,
            apikey=self.radarr_api_key,
        )

    def run(self):
        """Run the SeaDex Radarr syncer"""

        # Get all the anime movies
        all_radarr_movies = self.get_all_radarr_movies()
        n_radarr = len(all_radarr_movies)

        self.log_arr_start(
            arr="radarr",
            n_items=n_radarr,
        )

        # Now start looping over these movies
        for radarr_idx, radarr_movie in enumerate(all_radarr_movies):

            # Pull Radarr and database info out
            tmdb_id = radarr_movie.tmdbId
            imdb_id = radarr_movie.imdbId
            radarr_title = radarr_movie.title
            radarr_movie_id = radarr_movie.id

            self.log_arr_item_start(
                arr="radarr",
                item_title=radarr_title,
                n_item=radarr_idx + 1,
                n_items=n_radarr,
            )

            # If we're not monitored, then skip if ignore_unmonitored is switched on
            if not radarr_movie.monitored and self.ignore_unmonitored:
                self.log_arr_item_unmonitored(
                    arr="radarr",
                    item_title=radarr_title,
                )
                continue

            # Get the mappings from the Radarr movies to AniList
            al_mappings = self.get_anilist_ids(
                tmdb_id=tmdb_id,
                imdb_id=imdb_id,
                tmdb_type="movie",
            )

            if len(al_mappings) == 0:
                self.log_no_anilist_mappings(title=radarr_title)
                continue

            for anidb_id, mapping in al_mappings.items():

                # Map the TMDB ID through to AniList
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
                    arr="radarr",
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

                # Get the AniList title
                anilist_title = self.get_anilist_title(
                    al_id=al_id,
                    sd_entry=sd_entry,
                )

                radarr_release_dict = self.get_radarr_release_dict(
                    radarr_movie_id=radarr_movie_id
                )
                radarr_release_group = list(radarr_release_dict.keys())[0]

                self.logger.debug(
                    centred_string(
                        f"Radarr release group: {radarr_release_group}",
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

                # If we're in interactive mode and there are multiple options here, then select
                if self.interactive and len(seadex_dict) > 1:
                    seadex_dict = self.filter_seadex_interactive(
                        seadex_dict=seadex_dict,
                        sd_entry=sd_entry,
                    )

                seadex_dict = self.filter_seadex_downloads(
                    seadex_dict=seadex_dict,
                    arr="radarr",
                    arr_release_dict=radarr_release_dict,
                )

                # Check the release groups are matching, and get a bespoke list of torrents
                any_to_download = self.get_any_to_download(seadex_dict=seadex_dict)

                if any_to_download:
                    self.log_arr_seadex_mismatch(
                        arr="radarr",
                        seadex_dict=seadex_dict,
                    )
                    fields, anilist_thumb = self.get_seadex_fields(
                        arr="radarr",
                        al_id=al_id,
                        release_group=radarr_release_group,
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
                                arr_title=radarr_title,
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
                    arr="radarr",
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

    def get_all_radarr_movies(self):
        """Get all movies in Radarr that have an associated AniDB ID"""

        radarr_movies = []

        # Search through TMDB and IMDb IDs
        all_tmdb_ids = [
            self.anime_mappings[x].get("tmdb_movie_id", None)
            for x in self.anime_mappings
            if "tmdb_movie_id" in self.anime_mappings[x].keys()
        ]

        all_imdb_ids = [
            self.anime_mappings[x].get("imdb_id", None)
            for x in self.anime_mappings
            if "imdb_id" in self.anime_mappings[x].keys()
        ]

        for m in self.radarr.all_movies():

            # Check by TMDB IDs
            tmdb_id = m.tmdbId
            if tmdb_id in all_tmdb_ids and m not in radarr_movies:
                radarr_movies.append(m)

            # Check by IMDb IDs
            imdb_id = m.imdbId
            if imdb_id in all_imdb_ids and m not in radarr_movies:
                radarr_movies.append(m)

        radarr_movies.sort(key=lambda x: x.title)

        return radarr_movies

    def get_radarr_movie(self, tmdb_id=None, imdb_id=None):
        """Get Radarr movie for a given TMDB ID or IMDb ID

        Args:
            tmdb_id (int): TMDB movie ID
            imdb_id (str): IMDb movie ID
        """

        try:
            movie = self.radarr.get_movie(tmdb_id=tmdb_id, imdb_id=imdb_id)
        except arrapi.exceptions.NotFound:
            movie = None

        return movie

    def get_radarr_release_dict(
        self,
        radarr_movie_id,
    ):
        """Get a dictionary of useful info for a Radarr movie

        Args:
            radarr_movie_id (int): ID for movie in Radarr
        """

        # Get the movie file if it exists
        mov_req_url = (
            f"{self.radarr_url}/api/v3/moviefile?"
            f"movieId={radarr_movie_id}&"
            f"apikey={self.radarr_api_key}"
        )
        mov_req = requests.get(mov_req_url)

        radarr_release_dict = {
            r.get("releaseGroup", None): {"size": r.get("size", None)}
            for r in mov_req.json()
        }

        # If we have multiple options, throw up an error
        if len(radarr_release_dict) > 1:
            raise ValueError(f"Multiple files found for movie {radarr_movie_id}")

        # If we have nothing, return None
        elif len(radarr_release_dict) == 0:
            radarr_release_dict = {None: {"size": None}}

        return radarr_release_dict
