import copy

import requests

API_URL = "https://graphql.anilist.co"

# AniList query
QUERY = '''
query ($id: Int) {
  Media (id: $id, type: ANIME) {
    id
    title {
        english
        romaji
    }
    coverImage {
        extraLarge
        large
        medium
    }
    episodes
    format
  }
}
'''


def get_query(al_id):
    """Do the AniList query

    Args:
        al_id (int): Anilist ID
    """

    # Define query variables and values that will be used in the query request
    variables = {
        "id": al_id
    }

    resp = requests.post(API_URL, json={"query": QUERY, "variables": variables})
    j = resp.json()

    return j


def get_anilist_n_eps(al_id,
                      al_cache=None,
                      ):
    """Query AniList to get number of episodes for an anime.

    Args:
        al_id (int): Anilist ID
        al_cache (dict): Cached Anilist requests. Defaults to None,
            which will create a dictionary
    """

    # Try and find query in cache
    if al_cache is None:
        al_cache = {}
    j = al_cache.get(al_id, None)

    # If we don't have it, do the query
    if j is None:
        j = get_query(al_id)
        al_cache[al_id] = copy.deepcopy(j)

    # Pull out number of episodes
    n_eps = j["data"]["Media"]["episodes"]

    return n_eps, al_cache


def get_anilist_title(al_id,
                      al_cache=None,
                      ):
    """Query AniList to get title for an anime.

    Args:
        al_id (int): Anilist ID
        al_cache (dict): Cached Anilist requests. Defaults to None,
            which will create a dictionary
    """

    # Try and find query in cache
    if al_cache is None:
        al_cache = {}
    j = al_cache.get(al_id, None)

    # If we don't have it, do the query
    if j is None:
        j = get_query(al_id)
        al_cache[al_id] = copy.deepcopy(j)

    # Prefer the english title, but fall back to romaji
    title = j["data"]["Media"]["title"].get("english", None)
    if title is None:
        title = j["data"]["Media"]["title"].get("romaji", None)

    return title, al_cache


def get_anilist_thumb(al_id,
                      al_cache=None,
                      ):
    """Query AniList to get thumbnail URL for an anime.

    Args:
        al_id (int): Anilist ID
        al_cache (dict): Cached Anilist requests. Defaults to None,
            which will create a dictionary
    """

    # Try and find query in cache
    if al_cache is None:
        al_cache = {}
    j = al_cache.get(al_id, None)

    # If we don't have it, do the query
    if j is None:
        j = get_query(al_id)
        al_cache[al_id] = copy.deepcopy(j)

    thumb = j["data"]["Media"]["coverImage"]["large"]

    return thumb, al_cache


def get_anilist_format(al_id,
                       al_cache=None,
                       ):
    """Query AniList to get format for an anime.

    Args:
        al_id (int): Anilist ID
        al_cache (dict): Cached Anilist requests. Defaults to None,
            which will create a dictionary
    """

    # Try and find query in cache
    if al_cache is None:
        al_cache = {}
    j = al_cache.get(al_id, None)

    # If we don't have it, do the query
    if j is None:
        j = get_query(al_id)
        al_cache[al_id] = copy.deepcopy(j)

    al_format = j["data"]["Media"]["format"]

    return al_format, al_cache
