import platform
import selenium
import json
import os
import time
import datetime

import selenium.webdriver
from selenium.webdriver.common.by import By

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
            raise FileNotFoundError("No config.json file found")
        
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
    videoType = Column("Type", String)
    date = Column("Date", Date)

    def __init__(self, id:str, title:str, description:str, channel:str, date:datetime.datetime) -> None:
        self.id = id
        self.title = title
        self.description = description
        self.channel = channel
        self.date = date

engine = create_engine(f"sqlite:///{config.database}", echo=False)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()

class Bot:
    def __init__(self, config:Config) -> None:
        self.os:str = platform.system() # "Windows", "Linux"
        self.playlists:list[str] = self.__getplaylists__(config.channels)
        self.driver:selenium.webdriver.Firefox = self.__getdriver__(config)
        self.config:Config = config

        print(f"Logging to {self.config.logfile}") if self.config.logging else print("Logging disabled.")
        self.log(f"Bot initialized with {len(self.playlists)} channel(s) to check. Cycles every {self.config.sleepTime} seconds. Check range: {self.config.checkRange}.")

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
        print(foundVideos)
        self.driver.get("https://i.stack.imgur.com/kOnzy.gif")

    def insert(self, video:Video) -> None:
        """Inserts a Video object into the database or updates it if entry with this ID already exists."""
        vid = session.query(Video).filter(Video.id == video.id)
        if vid.first() is not None:
            vid.update({Video.title: video.title, Video.description: video.description, Video.channel: video.channel, Video.date: video.date})
        else:
            session.add(video)
        session.commit()

    def fetch(self, videoID:str) -> Video:
        """Returns a Video object from the database."""
        return session.query(Video).filter(Video.id == videoID).first()

    def __killalldrivers__(self) -> None:
        """Kills all running webdrivers."""
        match self.os.lower():
            case "linux":
                os.system("killall geckodriver")
                os.system("killall firefox")
            case "windows":
                os.system("taskkill /F /IM firefox.exe")
            case _:
                raise OSError("Unsupported operating system")

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

        match self.os.lower():
            case "linux":
                return selenium.webdriver.Firefox(options=options, service=os.path.join(os.getcwd(), "src", "geckodriver"))
            case "windows": 
                return selenium.webdriver.Firefox(options=options)
            case _:
                raise OSError("Unsupported operating system")
            
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
            
    def __getmetadata__(self, videoID:str) -> dict:
        """Returns Video object."""
        pass