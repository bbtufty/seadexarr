from urllib.parse import urljoin

import pynyaa
import requests
from bs4 import BeautifulSoup

ANIMETOSHO_FEED_URL = "https://animetosho.org/feed/json"


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

        if i["link"] == url:
            parsed_url = i["torrent_url"]

    return parsed_url
