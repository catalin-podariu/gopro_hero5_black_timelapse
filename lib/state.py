#!/usr/bin/env python3

# Loads and saves state from a JSON file (e.g., state.json).

import json
import datetime
import subprocess

from lib.logger import logger
from lib.util import from_iso_format_fallback
from lib.config import Config


class State:

    def __init__(self):
        config = Config()
        self.config = config

    def load_state(self):
        logger.info(f"Loading state. This only happens after a REBOOT. Current state is [{self.config.state}]")
        result = subprocess.run(["sudo", "uptime"], capture_output=True, text=True)
        logger.info(f"Uptime: {result.stdout.strip()}")

        try:
            with open(self.config.state_file_path, "r") as f:
                loaded_state = json.load(f)

            # Convert string timestamps back to datetime objects
            for key in ["last_photo_minute", "last_offline_alert_time"]:
                if key in loaded_state:
                    loaded_state[key] = from_iso_format_fallback(loaded_state[key])

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

    def save_state(self):
        data = {
            "last_photo_minute": self.config.last_photo_minute if self.config.last_photo_minute else None,
            "last_offline_alert_time": from_iso_format_fallback(
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
