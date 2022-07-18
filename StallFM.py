import musicbrainzngs as mb
import html
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import ssl
import json
from datetime import datetime
from datetime import timedelta
from http.client import HTTPSConnection
from urllib.parse import quote_plus
from xml.dom import Node, minidom
from flask import Flask

# You have to have your own unique two values for API_KEY and API_SECRET
# Obtain yours from https://www.last.fm/api/account/create for Last.fm
API_KEY = "b22a39da4c2100b1d8210bbd8e714e2c"
#API_SECRET = ""

#Last.fm username and password
username = ""

PERIOD_OVERALL = "overall"
PERIOD_7DAYS = "7day"
PERIOD_1MONTH = "1month"
PERIOD_3MONTHS = "3month"
PERIOD_6MONTHS = "6month"
PERIOD_12MONTHS = "12month"

app = Flask(__name__)

mb.set_useragent("StallFM", "1.2.0", username)

ALBUMS = "album"
TRACKS = "track"
RECENTTRACKS = "recenttracks"

SSL_CONTEXT = ssl.create_default_context()

class stallFM:
    def __init__(self,username,releasetype=ALBUMS, limit=1000, period=PERIOD_OVERALL, start_date="1970-01-01", end_date=datetime.today(),writetocsv=False):
        self.username = username
        self.limit = limit
        self.releasetype = releasetype
        self.start_date = start_date
        self.end_date = end_date
        self.writetocsv = writetocsv
        self.period = period
        self.df = None

    def create_dataframe(self):
        self.df = self.extract_top_releases()
        #self.df = self.add_mbid_info_to_dataframe()
        #self.df = self.remove_bad_releases_from_dataframe()
        self.df = self.df.head(self.limit)

        if self.writetocsv:
            self.write_csv_file()
        
    ###                     ###
    ###   DATA EXTRACTION   ###
    ###                     ###

    def extract_data(self,params):
        host_name = 'ws.audioscrobbler.com'
        host_subdir = '/2.0/'

        conn = HTTPSConnection(context=SSL_CONTEXT, host=host_name)

        data = []
        for name in params.keys():
            #data.append("=".join((name, quote_plus(_string(self.params[name])))))
            data.append('='.join((name,quote_plus(params[name]))))
        data = "&".join(data)

        url = '?' + data

        try:
            conn.request(url=host_subdir + url, body=data, method='POST')

            response = conn.getresponse()
            response_text = _unicode(response.read())
            doc = minidom.parseString(response_text.replace("opensearch:", ""))

            return doc

        except:
            print("connection error?")


    def get_params(self, page):
        params = {'method': 'user.gettop{}s'.format(self.releasetype), 'user': self.username, 'api_key': API_KEY, 'limit':'200', 'period': self.period, 'page': str(page)}

        return params

    def get_page_count(self):
        params = self.get_params(1)
        doc = self.extract_data(params)

        return int(doc.getElementsByTagName('top{}s'.format(self.releasetype))[0].getAttribute('totalPages'))

    def extract_top_releases(self):
        #directly extracts data from the last.fm .... Needs an internet connection.
        data =[]

        page_count = self.get_page_count()
        page_range = self.limit//200
        print(page_range)
        print(self.limit%200)

        for page in range(page_range):
            params = self.get_params(page+1)
            doc = self.extract_data(params)
            data.extend(_extract_top_albums(doc))

        #Generalize this for both albums and tracks!
        self.df = pd.DataFrame(data, columns =['Artist', 'Album', 'Play count','MBID'])

        return self.df


    ###                 ###
    ###  DATA CLEANING  ###
    ###                 ###

    def add_mbid_info_to_dataframe(self):
        #adds release year and release type to each release. NB! Time consuming.

        df = self.df

        mb_mbid = df.apply(lambda row: get_mbinfo_from_mbid(row['MBID']), axis=1)

        self.df[['Release year','Release type']] = pd.DataFrame(mb_mbid.to_list())

        #Need to implement a script that finds the release year for releases without an MBID
        #mb_search = df.apply(lambda row: get_mbinfo_from_search(df[df['MBID'].isna()]))

        return self.df

    def remove_bad_releases_from_dataframe(self):
        #Removes all type of releases except LPs, EPs, and singles from the dataframe
        self.df = self.df.drop(self.df[self.df['Release type'] == "Compilation"].index)
        self.df = self.df.drop(self.df[self.df['Release type'] == "Soundtrack"].index)
        self.df = self.df.drop(self.df[self.df['Release type'] == "Live"].index)
        self.df = self.df.drop(self.df[self.df['Release type'] == "Demo"].index)
        self.df = self.df.dropna()

        return self.df

    def find_and_replace_remaster(self,condition = 'Remaster|Version|Edition|Reissue|Deluxe|Expanded'):
        #Assume it's supposed to remove "dirty tags" from the dataframe. Not sure if it works as intended.
        df = self.df

        cond = df[self.releasetype].str.contains(condition, case=False)
        vocab = get_vocabulary()

        for phrase in vocab:
            df.loc[cond, self.releasetype] = df[self.releasetype].str.replace(phrase,"",regex = False, case = False)

        return df

    def get_top_album_per_year(self):
        #Returns the top played album for every original release year
        self.df = self.df.loc[self.df.groupby("Release year")["Play count"].idxmax()]
        
        return self.df

    def get_top_album_of_release_year(self,release_year,limit=10):
        #Returns the top played albums for a given year and prints to terminal
        df = self.df.loc[self.df['Release year'] == release_year]
        df = df.drop(['Release year'],axis=1)
        df = df.head(limit)
        
        print(df)
        
        #return self.df

    ###               ###
    ### RECENT TRACKS ###
    ###               ### 

    def sort_library(self):
        #Sorts the dataframe either by albums or tracks as chosen. 
        if self.releasetype == ALBUMS:
            self.df = self.sort_top_albums()
        elif self.releasetype == TRACKS:
            self.df = self.sort_top_tracks()
        elif self.releasetype == RECENTTRACKS:
            self.df = self.sort_recent_tracks()
        else:
            print("wrong releasetype")

        return self.df

    def sort_top_tracks(self):
        #Sorts the most played tracks of the library in descending order from raw scrobbledata
        self.df = self.df.drop(['Time stamp'], axis=1)
        self.df = self.df.groupby(self.df.columns.tolist(),as_index=False).size()
        self.df = self.df.rename(columns={'size': 'Play count'})
        self.df = self.df.sort_values(by=['Play count'],ascending=False)

        return self.df

    def sort_top_albums(self):
        #Sorts the most played albums of the user library in descending order from raw scrobbledata
        df = self.df

        try:
            df = df.drop(['Track','Time stamp'], axis=1)
            df = df.groupby(['Artist','Album'], as_index=False).size()
            df = df.rename(columns={'size': 'Play count'})
            df = df.sort_values(by=['Play count'],ascending=False)

        except:
            df = df.groupby(['Artist','Album'],as_index=False).sum()
            df = df.sort_values(by=['Play count'],ascending=False)

        self.df = df

        return df

    def get_time_interval(self):
        #Using data only for tracks scrobbled within two selected dates. Only for raw data?
        date = self.df['Time stamp']
        self.df = self.df[(date >= self.start_date) & (date <= self.end_date)]

        return self.df

    ###             ###
    ###     CSV     ###
    ###             ###

    def read_csv_file(self):
        #Reads a file corresponding to top X albums or top X tracks if it exists.
        try:
            if self.limit == None:
                filetext = ""
            else:
                filetext = "_" + str(self.limit)

            return pd.read_csv('top{}_{}s_{}.csv'.format(filetext,self.releasetype,self.username), dtype={'Release year': 'Int64'})
        
        except:
            print("No csv-file found")

    def write_csv_file(self):
        #Creates a csv-file
        if self.limit == None:
            limittxt = ""
        else:
            limittxt = "_" + str(self.limit)

        self.df.to_csv("top{}_{}s_{}.csv".format(limittxt,self.releasetype,self.username),index=False)

###                       ###
###     VISUALIZATION     ###
###                       ###

def plot_release_year(df,saveImage=False):
    #Plots a barplot of cumulative listens per album release year
    plt.figure(figsize=(8,14))
    sns.barplot(y=df["Release year"], x=df['Play count'],data=df,estimator=sum,ci=None,orient="h")
    if saveImage == True:
        plt.savefig("test.png",format="png")
    plt.show()

###                  ###
###     FUNCTIONS    ###
###                  ###

def _unicode(text):
    if isinstance(text, bytes):
        return str(text, "utf-8")
    elif isinstance(text, str):
        return text
    else:
        return str(text)

def _extract(node, name, index=0):
    #Extracts a value from the xml string

    nodes = node.getElementsByTagName(name)

    if len(nodes):
        if nodes[index].firstChild:
            return _unescape_htmlentity(nodes[index].firstChild.data.strip())
    else:
        return None

def _extract_top_albums(doc):
    seq = []
    condition = ['Remaster','Version','Edition','Reissue','Deluxe','Expanded']
    for node in doc.getElementsByTagName('album'):
        name = _extract(node, "name")
        '''
        match = next((x for x in condition if x in name), False)
        if match is not False:
            print(match)
        '''
        artist = _extract(node, "name", 1)
        playcount = _extract(node, "playcount")
        mbid = _extract(node,'mbid')
        #info = {"image": _extract_all(node, "image")}

        seq.append((artist, name, playcount,mbid))

    return seq

def testfunc(name,condition = 'Remaster|Reissue|Deluxe|Version|Edition|Expanded'):
    if condition in name:
        print(name)
    #vocab = get_vocabulary()

def get_vocabulary():
    with open('vocab.json') as json_file:
        return json.load(json_file)

def _unescape_htmlentity(string):

    # string = _unicode(string)

    mapping = html.entities.name2codepoint
    for key in mapping:
        string = string.replace("&%s;" % key, chr(mapping[key]))

    return string

###                 ###
###   MUSICBRAINZ   ###
###                 ###

def get_mbinfo_from_mbid(mbid):
    try:
        release_group = mb.browse_release_groups(release=mbid)

        release_date = release_group['release-group-list'][0]['first-release-date']
        release_year = release_date.split("-")[0]
        release_type = release_group['release-group-list'][0]['type']

        return release_year, release_type
    except:
        return None,None

def get_mbinfo_from_search(df):
    try:
        release_group = mb_network.search_release_groups("artist:" + df['artist'] + " AND " + "release:" + df['album'],limit=1)

        release_date = release_group['release-group-list'][0]['first-release-date']
        release_year = release_date.split("-")[0]
        release_type = release_group['release-group-list'][0]['type']

        name = release_group['release-group-list'][0]['artist-credit'][0]['name']
        title = release_group['release-group-list'][0]['title']

        release_title = release_group['release-group-list'][0]['title'].replace(',','').replace("’","'")

        if release_title.lower() == df['album'].lower():
            release_date = release_group['release-group-list'][0]['first-release-date']
            release_year = release_date.split("-")[0]
            release_type = release_group['release-group-list'][0]['type']

            return release_year, release_type

        else:
            return None,None

    except:
        #print("Couldn't add: ",self)
        return None,None


if __name__ == "__main__":
    test = stallFM("Stalldyr", limit=450, releasetype=ALBUMS, period=PERIOD_12MONTHS)
    test.create_dataframe()

    #test.extract_top_albums()
    #test.find_and_replace_remaster()
    #test.add_mbid_info_to_dataframe_two()
    #print(test.df[test.df['MBID'].isna()])

    #test.df = test.df.head(10)
    #test.plot_release_year()

    




'''
class Connection():
    def __init__(self, params=None):
        if params is None:
            params = {}

        self.params = {}

        for key in params:
            self.params[key] = _unicode(params[key])

        self.api_key = API_KEY

        self.params["api_key"] = self.api_key
        self.params["method"] = method_name

        #if network.is_caching_enabled():
            #self.cache = network._get_cache_backend()
'''