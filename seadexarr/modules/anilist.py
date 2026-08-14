import copy
import requests
import time

from requests_ratelimiter import LimiterSession
session = LimiterSession(per_minute=15, per_second=0.5)  # max 15 requests/min, 1 req/2sec

API_URL = "https://graphql.anilist.co"

# AniList query
QUERY = """
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
"""


def get_query(al_id):
    """Do the AniList query

    Args:
        al_id (int): Anilist ID
    """

    # Define query variables and values that will be used in the query request
    variables = {"id": al_id}

    # Attempt query up to 5 times, if rate limit is exceeded
    for i in range(5):
        try:
            resp = session.post(API_URL, json={"query": QUERY, "variables": variables})
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 60))
                print(f"Rate limit exceeded on attempt #{i+1}/5. Retrying in {retry_after}s.")
                time.sleep(retry_after + 1)
            else:
                print(f"An HTTP error occurred: {e}")
                break
        except requests.exceptions.RequestException as e:
            print(f"A general error occurred: {e}")
            break

    return resp.json()


def get_anilist_n_eps(
    al_id,
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
    n_eps = j.get("data", {}).get("Media", {}).get("episodes", None)

    return n_eps, al_cache


def get_anilist_title(
    al_id,
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
    title = j.get("data", {}).get("Media", {}).get("title", {}).get("english", None)
    if title is None:
        title = j.get("data", {}).get("Media", {}).get("title", {}).get("romaji", None)

    return title, al_cache


def get_anilist_thumb(
    al_id,
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

    thumb = j.get("data", {}).get("Media", {}).get("coverImage", {}).get("large", None)

    return thumb, al_cache


def get_anilist_format(
    al_id,
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

    al_format = j.get("data", {}).get("Media", {}).get("format", None)

    return al_format, al_cache
