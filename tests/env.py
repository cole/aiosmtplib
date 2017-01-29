import urllib.request


def network_available():
    try:
        urllib.request.urlopen('http://google.com', timeout=1)
    except OSError:
        return False
    else:
        return True


NETWORK_AVAILABLE = network_available()
