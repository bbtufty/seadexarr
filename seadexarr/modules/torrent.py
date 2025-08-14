from urllib.parse import urljoin, urlencode

import pynyaa
import requests
from bs4 import BeautifulSoup

ANIMETOSHO_FEED_URL = "https://animetosho.org/feed/json"
RUTRACKER_MAGNET_ANNOUNCE = "http://bt2.t-ru.org/ann?magnet"


def get_nyaa_url(url):
    """Get Nyaa torrent link from URL

    Args:
        url (str): URL to get Nyaa torrent link
    """

    nyaa = pynyaa.get(url)
    parsed_url = str(nyaa.torrent_file)

    return parsed_url


def get_animetosho_url(url):
    """Get AnimeTosho torrent link from URL

    Args:
        url (str): URL to get AnimeTosho torrent link
    """

    # Start by getting the webpage, so we can get a title
    r = requests.get(url)
    soup = BeautifulSoup(r.content, "html.parser")
    titles = soup.find_all("h2", attrs={"id": "title"})

    if len(titles) == 0:
        raise Exception("Could not find torrent name in AnimeTosho webpage")

    if len(titles) > 1:
        raise Exception("More than one torrent title in AnimeTosho webpage")

    title = titles[0].text

    # Fantastic, we have a title. Now query API
    query_url = urljoin(ANIMETOSHO_FEED_URL, f"?t=search&q={title}")
    r = requests.get(query_url)
    j = r.json()

    # Loop over, make sure the link matches the URL and get a torrent link out
    parsed_url = None
    for i in j:

        if parsed_url is not None:
            continue

        link = i.get("link", None)
        if link == url:
            parsed_url = i.get("torrent_url", None)

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
