#!/usr/bin/env python3

import json
import datetime

from gptl_logger import logger
from gptl_util import fromisoformat_fallback

class GptlState:

    def __init__(self, config_path="config/config.json"):
        self.config_path = config_path
        with open(config_path, "r") as f:
            self.config = json.load(f)

        self.state_path = self.config["state_path"]

        self.last_photo_minute = None
        self.last_offline_alert_time = None
        self.photo_capture_error_counter = 0
        self.reach_for_help_counter = 0
        self.error_retries_counter = 0
        self.max_error_retries = 5
        self.execution_start_time = datetime.datetime.now()
        self.restart_counter = 0


    def load_state(self):
        try:
            with open(self.state_path, "r") as f:
                state_data = json.load(f)

            # Convert string timestamps back to datetime objects
            for key in ["last_photo_minute", "last_offline_alert_time"]:
                if key in state_data:
                    state_data[key] = fromisoformat_fallback(state_data[key])
            return state_data
        except FileNotFoundError as e:
            logger.error(f"Error loading state file: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error loading state: {e}")
            return {}

    def save_state(self):
        data = {
            "last_photo_minute": self.last_photo_minute if self.last_photo_minute else None,
            "last_offline_alert_time": fromisoformat_fallback(self.last_offline_alert_time.isoformat()) if self.last_offline_alert_time else None,
            "photo_capture_error_counter": self.photo_capture_error_counter if self.photo_capture_error_counter else 0,
            "reach_for_help_counter": self.reach_for_help_counter if self.reach_for_help_counter else 0,
            "error_retries": self.error_retries_counter if self.error_retries_counter else 0,
            "max_error_retries": self.max_error_retries if self.max_error_retries else 5,
            "execution_time_seconds": (datetime.datetime.now() - self.execution_start_time).total_seconds(),
            "restart_counter": self.restart_counter if self.restart_counter else 0,
        }
        try:
            with open(self.state_path, "w") as f:
                json.dump(data, f, indent=4)
            logger.info(f"Saved state to {self.state_path}.")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")