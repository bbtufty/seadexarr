0.5.0 (Unreleased)
==================

- Include SeaDex tags in log and Discord messages
- Add options to ignore unmonitored series/movies
- Save logs to file
- Ensure SCHEDULE_TIME is brought in as a float
- Fix Discord messages not getting pushed if no torrent client selected
- Fix adding too many torrents in one go

0.4.1 (2025-07-31)
==================

- Add PyYAML to pyproject.toml
- Added support for AnimeTosho

0.4.0 (2025-07-31)
==================

- Added ignore_movies_in_radarr for SeaDexSonarr, which will skip movies flagged as Specials in Sonarr that already
  exist in Radarr
- More robust config when parameters added
- Build Docker for every main update
- Fix crash when AniDB mapping contains no text
- Use IMDb for finding AniList mappings as well
- Initial support for other trackers
- Better handle Discord notifications and log messages when torrent already in client
- Map potentially weird episodes SeaDexSonarr if in Season 0 (Specials)

0.3.0 (2025-07-30)
==================

- Added scheduling in Docker mode

0.2.0 (2025-07-30)
==================

- Add Docker support
- Move to config files, to make the call simpler
- Fix crash if torrent in list but not already downloaded

0.1.0 (2025-07-22)
==================

- Add support for Radarr

0.0.3 (2025-07-22)
==================

- Rename from seadex_sonarr to seadexarr, in preparation for Radarr support
- Add interactive mode, for selecting when multiple "best" options are found
- Add support for adding torrents to qBittorrent

0.0.2 (2025-07-13)
==================

- Improved Discord messaging
- Catch the case where we don't find any suitable SeaDex releases
- Include potentially weird offset mappings via AniDB lists
- Add a rest time to not hit AniList rate limiting

0.0.1 (2025-07-12)
==================

- Initial release
