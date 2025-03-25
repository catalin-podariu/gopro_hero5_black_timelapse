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

        self.state_file_path = self.config["heartbeat"]["state_file"]
        self.router_config = self.config["router"]
        self.gopro_config = self.config["gopro"]
        self.push_config = self.config["pushbullet"]
        self.photo_timer = self.config["photo_timer"]["minutes"]
        self.keep_alive_timer = self.config["keep_alive"]["minutes"]

        self.sending_alert_every_20_min = 0
        self.restart_counter = 0
        self.max_error_retries = 4
        self.error_retries_counter = 0
        self.photo_capture_error_counter = 0
        self.last_offline_alert_time = None
        self.last_photo_minute = None
        self.execution_start_time = None
        self.rpi_uptime = None

    def load_saved_config(self):
        logger.info(f"Loading state. This only happens after a REBOOT. Current state is [{self.state}]")
        result = subprocess.run(["sudo", "uptime"], capture_output=True, text=True)
        logger.info(f"Uptime: {result.stdout.strip()}")

        try:
            with open(self.state_file_path, "r") as f:
                loaded_state = json.load(f)

            # Convert string timestamps back to datetime objects
            for key in ["last_photo_minute", "last_offline_alert_time"]:
                if key in loaded_state:
                    loaded_state[key] = utilities.from_iso_format_fallback(loaded_state[key])

            self.sending_alert_every_20_min = loaded_state.get("sending_alert_every_20_min", False)
            self.restart_counter = loaded_state.get("restart_counter", -1)
            self.max_error_retries = loaded_state.get("max_error_retries", 5)
            self.error_retries_counter = loaded_state.get("error_retries_counter", 0)
            self.photo_capture_error_counter = loaded_state.get("photo_capture_error_counter", 0)
            self.last_offline_alert_time = loaded_state.get("last_offline_alert_time")
            self.last_photo_minute = loaded_state.get("last_photo_minute")
            self.execution_start_time = loaded_state.get("execution_start_time", datetime.datetime.now().isoformat())
            self.rpi_uptime = loaded_state.get("rpi_uptime", -1)

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
            "last_photo_minute": self.last_photo_minute if self.last_photo_minute else None,
            "last_offline_alert_time": utilities.from_iso_format_fallback(
                self.last_offline_alert_time) if self.last_offline_alert_time else None,
            "photo_capture_error_counter": self.photo_capture_error_counter if self.photo_capture_error_counter else 0,
            "error_retries": self.error_retries_counter if self.error_retries_counter else 0,
            "max_error_retries": self.max_error_retries if self.max_error_retries else 5,
            "execution_time_seconds": (datetime.datetime.now() - utilities.from_iso_format_fallback(self.execution_start_time)).total_seconds(),
            "restart_counter": self.restart_counter,
            "sending_alert_every_20_min": self.sending_alert_every_20_min
        }

        try:
            with open(self.state_file_path, "w") as f:
                json.dump(data, f, indent=4)
            logger.info(f"Saved state to {self.state_file_path}.")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

global_config = Config()
