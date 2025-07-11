import time

from discordwebhook import Discord


def discord_push(
    url,
    sonarr_title,
    al_title,
    fields,
    thumb_url,
):
    """Post a message to Discord

    Args:
        url (str): URL to post to
        sonarr_title (str): Title as in Sonarr
        al_title (str): Title as in AniList
        fields (list): List of dicts containing links
            for the fields
        thumb_url (str): URL for thumbnail
    """

    discord = Discord(url=url)
    discord.post(
        embeds=[
            {
                "author": {
                    "name": sonarr_title,
                    "url": "https://github.com/bbtufty/seadex-sonarr",
                },
                "title": al_title,
                "fields": fields,
                "thumbnail": {"url": thumb_url},
            }
        ],
    )

    # Sleep for a bit to avoid rate limiting
    time.sleep(1)

    return True
