PERIOD_OVERALL = "overall"
PERIOD_7DAYS = "7day"
PERIOD_1MONTH = "1month"
PERIOD_3MONTHS = "3month"
PERIOD_6MONTHS = "6month"
PERIOD_12MONTHS = "12month"


class Network:
    def __init__(self,username,urls):
        self.username = username
        self.urls = urls
    
    def _get_url(self, url_type):
        return "https://ws.audioscrobbler.com/2.0/?/{}".format(self.urls[url_type])

    def get_url(self):
        #name = _url_safe(self.get_name())
        name = 'test'

        return self._get_url("user") % {"name": name}

    def get_top_albums(self, period=PERIOD_OVERALL, limit=None, cacheable=True):
        """Returns the top albums played by a user.
        * period: The period of time. Possible values:
          o PERIOD_OVERALL
          o PERIOD_7DAYS
          o PERIOD_1MONTH
          o PERIOD_3MONTHS
          o PERIOD_6MONTHS
          o PERIOD_12MONTHS
        """

        params = self._get_params()
        params["period"] = period
        if limit:
            params["limit"] = limit

        doc = self._request(self.ws_prefix + ".getTopAlbums", cacheable, params)

        return _extract_top_albums(doc, self.network)

def _extract_top_albums(doc, network):
    # TODO Maybe include the _request here too?
    seq = []
    for node in doc.getElementsByTagName("album"):
        name = _extract(node, "name")
        artist = _extract(node, "name", 1)
        playcount = _extract(node, "playcount")
        info = {"image": _extract_all(node, "image")}

        seq.append(TopItem(Album(artist, name, network, info=info), playcount))

    return seq

def getTopAlbums():
    

    


    conn = HTTPSConnection(context=SSL_CONTEXT, host=host_name)

    url = "http://ws.audioscrobbler.com/2.0/?" + params


        