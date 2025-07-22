import time

from discordwebhook import Discord


def discord_push(
    url,
    arr_title,
    al_title,
    seadex_url,
    fields,
    thumb_url,
):
    """Post a message to Discord

    Args:
        url (str): URL to post to
        arr_title (str): Title as in Arr instance
        al_title (str): Title as in AniList
        seadex_url (str): URL to SeaDex page
        fields (list): List of dicts containing links
            for the fields
        thumb_url (str): URL for thumbnail
    """

    discord = Discord(url=url)
    discord.post(
        embeds=[
            {
                "author": {
                    "name": arr_title,
                    "url": "https://github.com/bbtufty/seadexarr",
                },
                "title": al_title,
                "description": seadex_url,
                "fields": fields,
                "thumbnail": {"url": thumb_url},
            }
        ],
    )

    # Sleep for a bit to avoid rate limiting
    time.sleep(1)

    return True
