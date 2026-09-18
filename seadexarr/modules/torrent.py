import re
from urllib.parse import quote, urljoin, urlencode

from pynyaa import Nyaa
import requests
from bs4 import BeautifulSoup

AB_URL = "https://animebytes.tv/torrent"
ANIMETOSHO_FEED_URL = "https://animetosho.org/feed/json"
RUTRACKER_MAGNET_ANNOUNCE = "http://bt2.t-ru.org/ann?magnet"


def get_animebytes_url(
    url: str,
    passkey: str,
):
    """Get AnimeBytes torrent link from URL

    Args:
        url (str): URL to get AnimeBytes torrent link
        passkey (str): Passkey for AnimeBytes. Find this on your profile
    """

    torrent_id = re.findall(r"torrentid=(\d+)", url)

    if len(torrent_id) != 1:
        raise Exception(f"Could not parse torrent ID from URL {url}")
    torrent_id = torrent_id[0]

    parsed_url = f"{AB_URL}/{torrent_id}/download/{passkey}"

    return parsed_url


def get_animetosho_url(url):
    """Get AnimeTosho torrent link from URL

    Args:
        url (str): URL to get AnimeTosho torrent link
    """

    # Start by getting the webpage, so we can get a title
    r = requests.get(url)
    soup = BeautifulSoup(r.content, "html.parser")
    links = soup.find_all("a", href=True)

    parsed_url = []
    for link in links:
        if link["href"].startswith("magnet:"):
            parsed_url.append(link["href"])

    if len(parsed_url) == 0:
        raise Exception("Failed to find magnet link")
    elif len(parsed_url) > 1:
        raise Exception("More than one magnet link in AnimeToSho webpage")

    parsed_url = parsed_url[0]

    return parsed_url


def get_nyaa_url(url, host):
    """Get Nyaa torrent link from URL

    Args:
        url (str): URL to get Nyaa torrent link
        host (str): Hostname used for Nyaa
    """

    with Nyaa(base_url=f"https://{host}/") as nyaa:
        parsed_url = nyaa.get(url).torrent.url

    return parsed_url


def get_rutracker_url(
    url,
    torrent_hash,
):
    """Get RuTracker torrent link from URL

    Args:
        url (str): URL to get RuTracker torrent link
        torrent_hash (str): Torrent hash
    """

    # Pull the torrent title from souping the URL
    r = requests.get(url)
    soup = BeautifulSoup(r.content, "lxml")
    main_title = soup.find("h1", attrs={"class": "maintitle"})
    torrent_title = main_title.text

    params = {
        "xt": f"urn:btih:{torrent_hash}",
        "tr": RUTRACKER_MAGNET_ANNOUNCE,
        "dn": torrent_title,
    }
    url_encoded = urlencode(params)
    parsed_url = f"magnet:?{url_encoded}"

    return parsed_url
