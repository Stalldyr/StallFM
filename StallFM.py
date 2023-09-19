from operator import index
import musicbrainzngs as mb
import html
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import ssl
import json
from datetime import datetime
from http.client import HTTPSConnection
from urllib.parse import quote_plus
from xml.dom import Node, minidom
from flask import Flask, render_template, request

app = Flask(__name__)

# You have to have your own unique two values for API_KEY and API_SECRET
# Obtain yours from https://www.last.fm/api/account/create for Last.fm
API_KEY = "b22a39da4c2100b1d8210bbd8e714e2c"
#API_SECRET = ""

#Last.fm username
username = ""

PERIOD_OVERALL = "overall"
PERIOD_7DAYS = "7day"
PERIOD_1MONTH = "1month"
PERIOD_3MONTHS = "3month"
PERIOD_6MONTHS = "6month"
PERIOD_12MONTHS = "12month"

mb.set_useragent("StallFM", "1.2.0", username)

ALBUMS = "album"
TRACKS = "track"
RECENTTRACKS = "recenttracks"

SSL_CONTEXT = ssl.create_default_context()

class stallFM:
    def __init__(self,username,releasetype=ALBUMS, limit=1000, period=PERIOD_OVERALL, start_date="1970-01-01", end_date=datetime.today(),file_dir=None, extra_variables = ['RELEASE YEAR','TYPE']):
        self.username = username
        self.limit = limit
        self.releasetype = releasetype
        self.start_date = start_date
        self.end_date = end_date
        self.period = period
        self.dir = file_dir
        self.var = extra_variables
        self.create_dataframe()

    def create_dataframe(self):
        if self.dir:
            self.df = self.read_csv_file()
        else: 
            self.df = self.extract_top_releases()
        
    ###                     ###
    ###   DATA EXTRACTION   ###
    ###                     ###

    def extract_data(self,params):
        host_name = 'ws.audioscrobbler.com'
        host_subdir = '/2.0/'

        conn = HTTPSConnection(context=SSL_CONTEXT, host=host_name)

        data = []
        for name in params.keys():
            data.append("=".join((name, quote_plus(str(params[name])))))
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


    def get_params(self, page, pagelimit):
        params = {'method': 'user.gettop{}s'.format(self.releasetype), 'user': self.username, 'api_key': API_KEY, 'limit': pagelimit, 'period': self.period, 'page': str(page)}

        return params

    def get_page_count(self):
        #delete??
        params = self.get_params(1)
        doc = self.extract_data(params)

        return int(doc.getElementsByTagName('top{}s'.format(self.releasetype))[0].getAttribute('totalPages'))

    def extract_top_releases(self):
        #Directly extracts data from last.fm XML. Requires an internet connection.
        
        data =[]

        page_range = self.limit//200

        for page in range(page_range):
            params = self.get_params(page+1,200)
            doc = self.extract_data(params)
            data.extend(_extract_top_releases(doc,self.releasetype))

        if self.limit%200 != 0:
            params = self.get_params(page_range+1,self.limit%200)
            doc = self.extract_data(params)
            data.extend(_extract_top_releases(doc,self.releasetype))
        
        #Generalize this for both albums and tracks!
        df = pd.DataFrame(data, columns =['ARTIST', self.releasetype.upper(), 'PLAYCOUNT','MBID'])

        return df

    ###                 ###
    ###  DATA CLEANING  ###
    ###                 ###

    def add_mbid_info_to_dataframe(self):
        #Adds release year and release type to each release from MBID. NB!: Time consuming.

        mb_mbid = self.df.apply(lambda row: get_mbinfo_from_mbid(row['MBID']), axis=1)

        self.df[['RELEASE YEAR','TYPE']] = pd.DataFrame(mb_mbid.to_list())

        #Need to implement a script that finds the release year for releases without an MBID
        #mb_search = df.apply(lambda row: get_mbinfo_from_search(df[df['MBID'].isna()]))

        return self.df

    def fix_missing_values(self):
        #mb_search = self.df.apply(lambda row: get_mbinfo_from_search(self.df[self.df['MBID'].isna()]))
        #mb_search = get_mbinfo_from_search(self.df.loc[self.df['MBID'].isna()])
        mb_search = get_mbinfo_from_search(self.df)

        print(mb_search)

    def remove_bad_releases_from_dataframe(self):
        #Removes all type of releases except LPs, EPs, and singles from the dataframe.
        #Also removes missing values from the dataframe
        self.df = self.df.drop(self.df[self.df['TYPE'] == "Compilation"].index)
        self.df = self.df.drop(self.df[self.df['TYPE'] == "Soundtrack"].index)
        self.df = self.df.drop(self.df[self.df['TYPE'] == "Live"].index)
        self.df = self.df.drop(self.df[self.df['TYPE'] == "Demo"].index)
        #self.df = self.df.dropna()

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
        self.df = self.df.loc[self.df.groupby("RELEASE YEAR")["PLAYCOUNT"].idxmax()]
        
        return self.df

    def get_top_album_of_release_year(self,release_year,limit=10):
        #Returns the top played albums released in a given year
        df = self.df.loc[self.df['RELEASE YEAR'] == release_year]
        df = df.drop(['RELEASE YEAR'],axis=1)
        df = df.head(limit)
        
        return df

    ###               ###
    ### RECENT TRACKS ###
    ###               ###

    #Useful if you want to select tracks within in a specific time interval. Otherwise use ....

    def sort_library(self):
        #Sorts the dataframe either by albums or tracks as chosen. 
        if self.releasetype == ALBUMS:
            self.df = sort_top_albums(self.df)
        elif self.releasetype == TRACKS:
            self.df = sort_top_tracks(self.df)
        elif self.releasetype == RECENTTRACKS:
            self.df = self.sort_recent_tracks()
        else:
            print("Wrong release type")

        return self.df

    def get_time_interval(self):
        #Using data only for tracks scrobbled within two selected dates. NB! Only for recenttracks, topalbums or toptracks that doesn't have timestamps
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

            return pd.read_csv('top{}_{}s_{}.csv'.format(filetext,self.releasetype,self.username), dtype={'RELEASE YEAR': 'Int64'})
        
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
    sns.barplot(y=df["RELEASE YEAR"], x=df['PLAYCOUNT'], data=df, estimator=sum, ci=None, orient="h")
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

def _extract_top_releases(doc,releasetype):
    seq = []
    condition = ['Remaster','Version','Edition','Reissue','Deluxe','Expanded']
    for node in doc.getElementsByTagName(releasetype.lower()):
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

def sort_top_tracks(df):
    #Sorts the most played tracks of the library in descending order from recenttracks
    df = df.drop(['Time stamp'], axis=1)
    df = df.groupby(df.columns.tolist(),as_index=False).size()
    df = df.rename(columns={'size': 'PLAYCOUNT'})
    df = df.sort_values(by=['PLAYCOUNT'],ascending=False)

    return df

def sort_top_albums(df):
    #Sorts the most played albums of the user library in descending order from recent tracks

    try:
        df = df.drop(['Track','Time stamp'], axis=1)
        df = df.groupby(['Artist','Album'], as_index=False).size()
        df = df.rename(columns={'size': 'PLAYCOUNT'})
        df = df.sort_values(by=['PLAYCOUNT'],ascending=False)

    except:
        df = df.groupby(['Artist','Album'],as_index=False).sum()
        df = df.sort_values(by=['PLAYCOUNT'],ascending=False)

    return df

###                 ###
###   MUSICBRAINZ   ###
###                 ###

def get_mbinfo_from_mbid(mbid):
    try:
        release_group = mb.browse_release_groups(release=mbid, includes=["tags"])

        release_date = release_group['release-group-list'][0]['first-release-date']
        release_year = release_date.split("-")[0]
        release_type = release_group['release-group-list'][0]['type']
        #genre = release_group['release-group-list'][0]['tag-list']

        return release_year, release_type
    except:
        return None, None

def get_mbinfo_from_search(df):
    try:
        release_group = mb.search_release_groups("artist:" + df['artist'] + " AND " + "release:" + df['album'],limit=1)

        release_date = release_group['release-group-list'][0]['first-release-date']
        release_year = release_date.split("-")[0]
        release_type = release_group['release-group-list'][0]['type']

        #name = release_group['release-group-list'][0]['artist-credit'][0]['name']
        #title = release_group['release-group-list'][0]['title']

        release_title = release_group['release-group-list'][0]['title'].replace(',','').replace("’","'")

        if release_title.lower() == df['album'].lower():
            release_date = release_group['release-group-list'][0]['first-release-date']
            release_year = release_date.split("-")[0]
            release_type = release_group['release-group-list'][0]['type']

            return release_year, release_type

        else:
            return None,None

    except:
        print("Couldn't add: ")
        return None,None


if __name__ == "__main__":
    lastfm_data = stallFM("Stalldyr", limit=10, releasetype=ALBUMS)
    #lastfm_data.fix_missing_values()
    #lastfm_data.add_mbid_info_to_dataframe()
    #lastfm_data.remove_bad_releases_from_dataframe()
    #sorted_lastfm_data= lastfm_data.get_top_album_of_release_year(release_year="1991")

    print(lastfm_data.df)

    #app.run(debug=True)


@app.route("/form")
def form():
    return render_template("form.html")
    

@app.route("/data", methods=["POST"])
def data():
    lastfm_form = request.form
    lastfm_data = stallFM(lastfm_form["username"], limit=int(lastfm_form["limit"]), releasetype=lastfm_form["releasetype"])
    lastfm_data.create_dataframe()
    #lastfm_data.fix_missing_values()
    lastfm_data.add_mbid_info_to_dataframe()
    lastfm_data.remove_bad_releases_from_dataframe()
    sorted_lastfm_data= lastfm_data.get_top_album_of_release_year(release_year=int(lastfm_form["release_year"]))
    return sorted_lastfm_data.to_html()


@app.route("/test")
def hello_tester():
    return "<p>hello tester!</p>"


###Run sequence###
#env:FLASK_APP="StallFM\StallFM"
#env:FLASK_ENV="development"
#flask run
