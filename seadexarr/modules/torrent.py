import pynyaa


def get_nyaa_url(url):
    """Get Nyaa torrent link from URL

    Args:
        url (str): URL to get Nyaa torrent link
    """

    nyaa = pynyaa.get(url)
    parsed_url = str(nyaa.torrent_file)

    return parsed_url
