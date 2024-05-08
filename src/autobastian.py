import platform
import selenium
import json
import os
import time
import datetime
import html

import selenium.common
import selenium.webdriver
import selenium.webdriver.common
from selenium.webdriver.common.by import By

import selenium.webdriver.firefox
import selenium.webdriver.firefox.firefox_binary
import selenium.webdriver.firefox.service
import selenium.webdriver.remote
import selenium.webdriver.remote.webelement
from sqlalchemy import create_engine, Column, Integer, String, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

class Config:
    channels:list[str] = None #list of channel IDs
    headless:bool = False
    ignoreErrors:bool = True

    # Metadata settings
    metadataSource:str = None #"page", None or API key
    metadataRefresh:bool = False # choosing if every update cycle should check for metadata updates
    downloadFormat:str = "mp4"

    logging:bool = True # logging to a file
    sleepTime:int = 300
    waitTime:int = 5
    checkRange:int = 5
    outputFolder:str = None
    logfile:str = "autobastian.log"
    database:str = "autobastian.db"

    def __init__(self):
        try:
            with open("config.json", "r") as file:
                config = json.load(file)
        except FileNotFoundError:
            raise FileNotFoundError("Config.json not found.")
        
        for key, value in config.items():
            setattr(self, key, value)
        
        if self.channels is None or self.channels == []: raise ValueError("No channels provided in config.json")
        if self.ignoreErrors is None: self.ignoreErrors = True
        if self.waitTime < 0: raise ValueError("waitTime must be a positive integer")
        if self.sleepTime < 0: raise ValueError("sleepTime must be a positive integer")
        if self.checkRange < 0: raise ValueError("checkRange must be a positive integer")

config = Config()

global Base, session
Base = declarative_base()

class Video(Base):
    __tablename__ = "videos"

    entry = Column("Entry", Integer, primary_key=True)
    id = Column("ID", String)
    title = Column("Title", String)
    description = Column("Description", String)
    channel = Column("Channel", String)
    type = Column("Type", String)
    date = Column("Date", Date)

    def __init__(self, id:str, title:str, description:str, channel:str, type:str, date:datetime.date) -> None:
        self.id = id
        self.title = title
        self.description = description
        self.channel = channel
        self.type = type
        self.date = date

engine = create_engine(f"sqlite:///{config.database}", echo=False)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()

class Bot:
    def __init__(self, config:Config) -> None:
        if platform.system() != "Windows": raise OSError("This software is only compatible with Windows. Please check the documentation for Linux support.")
        self.playlists:list[str] = self.__getplaylists__(config.channels)
        self.driver:selenium.webdriver.Firefox = self.__getdriver__(config)
        self.config:Config = config

        print(f"Logging to {self.config.logfile}") if self.config.logging else print("Logging disabled.")
        self.log(f"Bot initialized with {len(self.playlists)} channel(s) to check. Sleeps between cycles for {self.config.sleepTime} second(s). Check range: {self.config.checkRange}.")

    def log(self, message:str) -> None:
        """Logs a message to the console and a log file."""
        now = datetime.datetime.now()
        year = now.year
        log_datetime = now.strftime(f'%d-%m-{year} | %H:%M:%S')

        log_message = f'[{log_datetime}] {message}'

        print(log_message)

        if not self.config.logging: return

        if not os.path.exists(self.config.logfile): open(self.config.logfile, 'w').close()

        with open(self.config.logfile, 'a', encoding = 'utf-8') as log_file:
            log_file.write(f'{log_message}\n')
        return

    def cycle(self) -> None:
        """Cycles through the playlists and checks for new uploads. Downloads new findings and saves data in the database."""
        foundVideos = []
        for playlist in self.playlists: foundVideos += self.__checkplaylist__(playlist)
        for videoID in foundVideos:
            vidObj = self.__getmetadata__(videoID)
            if vidObj is None: continue #premiere or scheduled livestream
            if self.config.metadataRefresh or self.fetch(videoID) is None: self.insert(vidObj)
        self.driver.get("https://muno.pl/wp-content/uploads/2017/12/a8d1d555c41cc07a32eb7d5072bd7f2e-850x570.jpg")

    #database functions
    def insert(self, video:Video) -> None:
        """Inserts a Video object into the database or updates it if entry with this ID already exists."""
        vid:Video = session.query(Video).filter(Video.id == video.id)
        dbEntry:Video = vid.first()
        if dbEntry is not None:
            if dbEntry.type == "live": video.date = dbEntry.date #prevents live streams from being updated if they go past midnight
            if self.__metadataChanged__(dbEntry, video):
                vid.update({Video.title: video.title, Video.description: video.description, Video.channel: video.channel, Video.date: video.date})
            else : return
        else:
            session.add(video)
        session.commit()
        self.log(f"Updated {video.id} metadata.")

    def fetch(self, videoID:str) -> Video:
        """Returns a Video object from the database."""
        return session.query(Video).filter(Video.id == videoID).first()

    def __getplaylists__(self, channels:list[str]) -> list[str]:
        """Translating channel IDs to channel playlists, raises ValueError if invalid channel ID is found."""
        playlists:list[str] = []
        for channel in channels:            
            if channel.startswith("UC") and len(channel) == 24:
                playlists.append(f"https://www.youtube.com/playlist?list=UU{channel[2:]}")
            elif channel.startswith("UU") and len(channel) == 24:
                playlists.append(f"https://www.youtube.com/playlist?list={channel}")
            else:
                raise ValueError(f"Invalid channel ID: {channel}")
            
        return playlists
    
    def __getdriver__(self, config:Config) -> selenium.webdriver.Firefox:
        """Returns a selenium webdriver depending on the operating system."""
        
        options = selenium.webdriver.FirefoxOptions()
        if config.headless: options.add_argument("-headless")
        options.add_argument("-profile")
        options.add_argument(os.path.join(os.getcwd(), "FirefoxProfile"))

        return selenium.webdriver.Firefox(options=options)
            
    def __checkplaylist__(self, playlist:str) -> list[str]:
        """Checks a playlist for new uploads and returns them as list of IDs."""
        self.driver.get(playlist)
        time.sleep(self.config.waitTime)
        videos = self.driver.find_elements(By.ID, "video-title")
        videoIDs = []
        for i, video in enumerate(videos):
            if i == self.config.checkRange: break
            videoIDs.append(video.get_attribute("href").split("watch?v=")[1][:11])
        return videoIDs
            
    def __getmetadata__(self, videoID:str) -> Video:
        """Gathers metadata and returns Video object."""
        match self.config.metadataSource:
            case "page":
                self.driver.get(f"https://www.youtube.com/watch?v={videoID}")
                time.sleep(self.config.waitTime)

                self.driver.find_element(By.ID, "expand").click()
                time.sleep(1) #needed for the description to load

                try:    
                    dateElem = self.driver.find_element(By.CSS_SELECTOR, "span.bold:nth-child(3)").text
                except selenium.common.exceptions.NoSuchElementException:
                    dateElem = self.driver.find_element(By.CSS_SELECTOR, "#info-container > yt-formatted-string:nth-child(3) > span:nth-child(1)").text
                split = dateElem.split(" ")

                type = "video"

                for part in split:
                    if part.lower().startswith("stream"): type = "live"
                    if part.lower().startswith("schedule") or part.lower().startswith("premier"): return None


                channel = self.driver.find_element(By.CSS_SELECTOR, "#text > a").text
                title = self.driver.find_element(By.CSS_SELECTOR, "#title > h1 > yt-formatted-string").text
                description = ""
                i = 1
                while True:
                    try:
                        part = self.driver.find_element(By.CSS_SELECTOR, f"yt-attributed-string.ytd-text-inline-expander:nth-child(1) > span:nth-child(1) > span:nth-child({i})")
                        description += self.__descriptionReconstructor__(part)
                        i += 1
                    except selenium.common.exceptions.NoSuchElementException:
                        break
                

                month, day, year = split[-3], split[-2].replace(",",""), split[-1]
                months = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6, "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}
                try:
                    date = datetime.datetime.strptime(f"{day}-{months[month]}-{year}","%d-%m-%Y").date()
                except:
                    type = "live"
                    date = datetime.datetime.now().date()

                return Video(videoID, title, description, channel, type, date)
            
            # TODO case "api":

            case _: pass

    def __descriptionReconstructor__(self, description:selenium.webdriver.remote.webelement.WebElement) -> str:
        """Reconstructs the description to be more readable."""
        span = description.find_elements(By.TAG_NAME, "span")
        a = description.find_elements(By.TAG_NAME, "a")

        if len(span) == 0 and len(a) == 0: return description.get_attribute("innerHTML")
        elif len(span) != 0: inner = span[0].find_element(By.TAG_NAME, "a")
        else: inner = a[0]

        if inner.text.startswith("#"): return inner.get_attribute("innerHTML")

        try:
            readableText = inner.get_attribute("href").split("&q=")[1]
        except IndexError:
            readableText = inner.get_attribute("href")
        
        readableText = readableText.split("&v=")[0]
        readableText = readableText.replace("%3A", ":")
        readableText = readableText.replace("%2F", "/")
        readableText = readableText.replace("%3F", "?")
        readableText = readableText.replace("%3D", "=")

        return readableText
    
    def __metadataChanged__(self, dbEntry:Video, video:Video) -> bool:
        """Checks if the metadata of a video has changed."""
        if (dbEntry.title != video.title) or (dbEntry.description != video.description) or (dbEntry.channel != video.channel) or (dbEntry.date != video.date): return True
        else: return False