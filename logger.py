#!/usr/bin/env python3

import os
import json
import logging
import logging.handlers
import types
import time
import re


CONFIG_PATH = "config.json"
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)
    LOG_DIR = config.get("logging_path", "./logs")
else:
    # Fallback defaults if config.json doesn't exist
    LOG_DIR = "/home/timelapse/logs/"

os.makedirs(LOG_DIR, exist_ok=True)

# 1) Custom "daily" handler that updates the active filename each midnight
class DailyNamedFileHandler(logging.handlers.TimedRotatingFileHandler):
    """
    A custom TimedRotatingFileHandler that uses a daily-based filename
    for the active log, e.g. 'daily_logs_2025_01_23.log'.
    At midnight, it renames the old log and updates to today's file name.
    """

    def __init__(self, directory, prefix="daily_logs", date_format="%Y_%m_%d",
                 when="midnight", interval=1, backupCount=0, encoding=None,
                 delay=False, utc=False):
        self.directory = directory
        self.prefix = prefix
        self.date_format = date_format

        # Start with today's filename
        filename = self._current_filename()
        super().__init__(
            filename=filename,
            when=when,
            interval=interval,
            backupCount=backupCount,
            encoding=encoding,
            delay=delay,
            utc=utc,
        )

        # Adjust how old files are renamed (optional)
        self.suffix = date_format
        self.extMatch = re.compile(r"^\d{4}_\d{2}_\d{2}$")

    def _current_filename(self):
        # e.g. "daily_logs_2025_01_23.log"
        datestr = time.strftime(self.date_format)
        return os.path.join(self.directory, f"{self.prefix}_{datestr}.log")

    def doRollover(self):
        # Let parent handle the actual rotation of the old file
        super().doRollover()

        # Now update self.baseFilename to today's new file
        new_name = self._current_filename()
        self.baseFilename = os.path.abspath(new_name)

        # If not delaying the stream, reopen immediately
        if not self.delay:
            self.stream = self._open()


# Create a custom formatter that can omit timestamps if 'plain' is set
class PlainFormatter(logging.Formatter):
    def format(self, record):
        if getattr(record, "plain", False):
            return record.getMessage()
        else:
            return super().format(record)

logger = logging.getLogger("CentralLogger")
logger.setLevel(logging.DEBUG)

file_handler = DailyNamedFileHandler(
    directory=LOG_DIR,
    prefix="daily_logs",
    date_format="%Y_%m_%d",
    when="midnight",
    interval=1,
    backupCount=0
)
file_handler.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)

# Normal log format for non-plain messages
normal_format_str = "%(asctime)s - %(levelname)s - %(message)s"

# Create a single PlainFormatter instance for both handlers
plain_formatter = PlainFormatter(normal_format_str)

file_handler.setFormatter(plain_formatter)
console_handler.setFormatter(plain_formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Monkey-patch a logo() method onto the logger
def logo_method(self):
    for line in intro_logo.strip("\n").splitlines():
        # Use extra={"plain": True} so the PlainFormatter prints raw text
        self.log(logging.INFO, line, extra={"plain": True})

logger.logo = types.MethodType(logo_method, logger)

intro_logo = r"""
.                                                                                           .


                     .d8888b.           8888888b.                                     
                    d88P  Y88b          888   Y88b                        o           
                    888    888          888    888                       d8b          
                    888         .d88b.  888   d88P 888d888  .d88b.      d888b         
                    888  88888 d88""88b 8888888P"  888P"   d88""88b "Y888888888P"     
                    888    888 888  888 888        888     888  888   "Y88888P"       
                    Y88b  d88P Y88..88P 888        888     Y88..88P   d88P"Y88b       
                     "Y8888P88  "Y88P"  888        888      "Y88P"   dP"     "Yb      
        88888888888 d8b                        888                                    
            888     Y8P                        888                                    
            888                                888                                    
            888     888 88888b.d88b.   .d88b.  888  8888b.  88888b.  .d8888b   .d88b. 
            888     888 888 "888 "88b d8P  Y8b 888     "88b 888 "88b 88K      d8P  Y8b
            888     888 888  888  888 88888888 888 .d888888 888  888 "Y8888b. 88888888
            888     888 888  888  888 Y8b.     888 888  888 888 d88P      X88 Y8b.    
            888     888 888  888  888  "Y8888  888 "Y888888 88888P"   88888P'  "Y8888 
                                                            888                       
                                                            888                       
                                                            888  script by @mrbigheart


.                                                                                           .
        """
