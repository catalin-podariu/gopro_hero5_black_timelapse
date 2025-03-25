#!/usr/bin/env python3

import json
import subprocess
import datetime

from lib import utilities
from lib.logger import logger


class Config:

    def __init__(self, config_path="/home/timelapse/config.json"):
        self.config_path = config_path
        with open(config_path, "r") as f:
            self.config = json.load(f)

        self.state = "WAITING"
        self.state_file_path = "state.json"

        self.router_config = self.config["router"]
        self.gopro_config = self.config["gopro"]
        self.push_config = self.config["pushbullet"]
        self.photo_timer = self.config["photo_timer"]["minutes"]
        self.keep_alive_timer = self.config["keep_alive"]["minutes"]

        self.sending_alert_every_20_min = None
        self.restart_counter = 0
        self.max_error_retries = None
        self.error_retries_counter = None
        self.photo_capture_error_counter = 0
        self.last_offline_alert_time = None
        self.last_photo_minute = None
        self.execution_start_time = None

    def reload_config(self):
        """
        Re-read 'config.json' from disk and update all relevant fields
        (wifi_config, gopro_config, rpi, push_config, photo_timer, etc.).
        """
        try:
            with open(self.config_path, "r") as f:
                new_config = json.load(f)

            # Update everything you need
            self.router_config = new_config["router"]
            self.gopro_config = new_config["gopro"]
            self.push_config = new_config["pushbullet"]
            self.photo_timer = new_config["photo_timer"]["minutes"]
            self.keep_alive_timer = new_config["keep_alive"]["minutes"]

            self.config = new_config

            logger.info("New config loaded successfully..")
        except Exception as e:
            logger.error(f"Failed to load new config: {e}")

    def load_saved_config(self):
        logger.info(f"Loading state. This only happens after a REBOOT. Current state is [{global_config.state}]")
        result = subprocess.run(["sudo", "uptime"], capture_output=True, text=True)
        logger.info(f"Uptime: {result.stdout.strip()}")

        try:
            with open(self.config.state_file_path, "r") as f:
                loaded_state = json.load(f)

            # Convert string timestamps back to datetime objects
            for key in ["last_photo_minute", "last_offline_alert_time"]:
                if key in loaded_state:
                    loaded_state[key] = utilities.from_iso_format_fallback(loaded_state[key]) #.isoformat() ?!

            self.config.last_photo_minute = loaded_state.get("last_photo_minute")
            self.config.last_offline_alert_time = loaded_state.get("last_offline_alert_time")
            self.config.photo_capture_error_counter = loaded_state.get("photo_capture_error_counter", 0)
            self.config.error_retries_counter = loaded_state.get("error_retries", 0)
            self.config.max_error_retries = loaded_state.get("max_error_retries", 5)
            self.config.restart_counter = loaded_state.get("restart_counter", -1)
            self.config.sending_alert_every_20_min = loaded_state.get("sending_alert_every_20_min", False)

            logger.info("New stat is loaded and all saved variables are rehydrated.")
            return loaded_state
        except FileNotFoundError as e:
            logger.error(f"Error loading state file: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error loading state: {e}")
            return {}

    def save_current_configs(self):
        data = {
            "last_photo_minute": self.config.last_photo_minute if self.config.last_photo_minute else None,
            "last_offline_alert_time": utilities.from_iso_format_fallback(
                self.config.last_offline_alert_time.isoformat()) if self.config.last_offline_alert_time else None,
            "photo_capture_error_counter": self.config.photo_capture_error_counter if self.config.photo_capture_error_counter else 0,
            "error_retries": self.config.error_retries_counter if self.config.error_retries_counter else 0,
            "max_error_retries": self.config.max_error_retries if self.config.max_error_retries else 5,
            "execution_time_seconds": (datetime.datetime.now() - self.config.execution_start_time).total_seconds(),
            "restart_counter": self.config.restart_counter,
            "sending_alert_every_20_min": self.config.sending_alert_every_20_min
        }

        try:
            with open(self.config.state_file_path, "w") as f:
                json.dump(data, f, indent=4)
            logger.info(f"Saved state to {self.config.state_file_path}.")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

global_config = Config()
