import pylast
import musicbrainzngs as mb
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy
from datetime import datetime
from datetime import timedelta

# You have to have your own unique two values for API_KEY and API_SECRET
# Obtain yours from https://www.last.fm/api/account/create for Last.fm
API_KEY = ""
API_SECRET = ""

#Last.fm username and password
username = ""
password_hash = pylast.md5("")

network = pylast.LastFMNetwork(
    api_key=API_KEY,
    api_secret=API_SECRET,
    username=username,
    password_hash=password_hash,
)

user = pylast.User(username,network)
mb.set_useragent("StallFM", "1.2.0",username)

ALBUMS = "albums"
TRACKS = "tracks"


class stallFM:
    def __init__(self,toptype=ALBUMS,limit=None, start_date = datetime(1970,1,1),end_date=datetime.today(),writetocsv=False):
        self.limit = limit
        self.toptype = toptype
        self.start_date = start_date
        self.end_date = end_date
        self.writetocsv = writetocsv
        self.album_data = None
    
    def __repr__(self):
        return self.album_data

    def get_top_albums_data(self, writetocsv=False):
        #Uses Last.fm API in order to recieve user top albums and add release year and release type. 
        #Limited to 1000 albums at most. 

        top_albums = user.get_top_albums(limit=self.limit)

        album_artists = []
        album_titles = []
        release_years = []
        release_types = []
        user_play_counts = []
        for albums in top_albums:
            album = pylast.Album(albums[0].artist,albums[0].title, network, username=username)
            
            release_year, release_type = album.get_mbinfo(mb)

            album_artists.append(album.artist)
            album_titles.append(album.title)
            release_years.append(release_year)
            release_types.append(release_type)
            user_play_counts.append(album.get_userplaycount())
            
        data = {'Artist': album_artists, 'Title': album_titles, 'Release year': release_years, 'Release type': release_types, 'Play count': user_play_counts}
        album_data = pd.DataFrame(data = data)

        if writetocsv:
            album_data.to_csv("top_{}_albums.csv".format(limit),index=False)

        return album_data

    def add_mbid_info_to_dataframe(self):
        #Adds release year and release type to an excisting dataframe.
        release_years = []
        release_types = []
        for index,release in self.album_data.iterrows():
            album = pylast.Album(release['Artist'],release['Album'], network,username=username)

            release_year, release_type = album.get_mbinfo(mb)

            release_years.append(release_year)
            release_types.append(release_type)
        
        self.album_data['Release year'] = release_years
        self.album_data['Release type'] = release_types

        if self.writetocsv:
            self.album_data.to_csv("top_{}_albums.csv".format(self.album_data.shape[0]),index=False)

        return self.album_data

    def clean_data(self):
        #Removes bad values from the dataframe
        self.album_data = self.album_data.drop(self.album_data[self.album_data['Release type'] == "Compilation"].index)
        self.album_data = self.album_data.drop(self.album_data[self.album_data['Release type'] == "Soundtrack"].index)
        self.album_data = self.album_data.drop(self.album_data[self.album_data['Release type'] == "Live"].index)
        self.album_data = self.album_data.drop(self.album_data[self.album_data['Release type'] == "Demo"].index)
        self.album_data = self.album_data.dropna()

        return self.album_data

    def plot_release_year(self,saveImage=False):
        #Plots a barplot of cumulative listens per album release year
        plt.figure(figsize=(8,14))
        sns.barplot(y=self.album_data["Release year"], x=self.album_data['Play count'],data=self.album_data,estimator=sum,ci=None,orient="h")
        if saveImage == True:
            plt.savefig("test.png",format="png")
        plt.show()

    def get_top_album_per_year(self):
        #Returns the top played album for every original release year
        self.album_data = self.album_data.loc[self.album_data.groupby("Release year")["Play count"].idxmax()]
        
        return self.album_data

    def get_top_album_of_release_year(self,release_year,limit=10):
        #Returns the top played albums for a given year and prints to terminal
        album_data = self.album_data.loc[self.album_data['Release year'] == release_year]
        album_data = album_data.drop(['Release year'],axis=1)
        album_data = album_data.head(limit)
        
        print(album_data)
        
        #return self.album_data

    def get_top_tracks(self):
        #Sorts the most played tracks of the library in descending order
        self.album_data = self.album_data.drop(['Time stamp'], axis=1)
        self.album_data = self.album_data.groupby(self.album_data.columns.tolist(),as_index=False).size()
        self.album_data = self.album_data.rename(columns={'size': 'Play count'})
        self.album_data = self.album_data.sort_values(by=['Play count'],ascending=False)

        return self.album_data

    def get_top_albums(self):
        #Sorts the most played albums of the library in descending order
        self.album_data = self.album_data.drop(['Title','Time stamp'], axis=1)
        self.album_data = self.album_data.groupby(self.album_data.columns.tolist(),as_index=False).size()
        self.album_data = self.album_data.rename(columns={'size': 'Play count'})
        self.album_data = self.album_data.sort_values(by=['Play count'],ascending=False)

        return self.album_data

    def get_library_csv(self):
        #Reads the csv-file containing user library gotten from https://benjaminbenben.com/lastfm-to-csv/
        try:
            album_data = pd.read_csv("{}.csv".format(username),header=None)
            album_data.columns = ['Artist','Album','Title','Time stamp']
            album_data['Time stamp'] =  pd.to_datetime(album_data['Time stamp'], format="%d %b %Y %H:%M")

            self.album_data = album_data
        except:
            print("Missing library-file")

        return self.album_data

    def get_time_interval(self):
        #Using data only for tracks scrobbled within two selected dates.
        date = self.album_data['Time stamp']
        self.album_data = self.album_data[(date >= self.start_date) & (date <= self.end_date)]

        return self.album_data

    def read_top_file(self):
        #Reads a file corresponding to top X albums or top X tracks if it already exists, or creates one if it doesn't.
        try:
            if self.limit == None:
                filetext = ""
            else:
                filetext = "_" + str(self.limit) + "_"
            album_data = pd.read_csv('top{}{}.csv'.format(filetext,self.toptype), dtype={'Release year': 'Int64'})
            
            self.album_data = album_data

            return self.album_data
        except:
            self.album_data = self.get_library_csv()
            self.album_data = self.get_time_interval()
            self.album_data = self.get_top_albums()
            self.album_data = self.album_data.head(self.limit)

            return self.album_data

test = stallFM(limit=150,start_date=datetime(2021,1,1),writetocsv=True)
test.read_top_file()
test.clean_data()

for i in range(1971,2021):
    test.get_top_album_of_release_year(i,limit=1)
