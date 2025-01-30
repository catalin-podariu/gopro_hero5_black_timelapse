#!/usr/bin/env python3

import json

from gptl_logger import logger


class GptlConfig:
    def __init__(self, config_path="config/config.json"):
        self.config_path = config_path
        with open(config_path, "r") as f:
            self.config = json.load(f)

        self.router_config = self.config["router"]
        self.gopro_config = self.config["gopro"]
        self.debug_level = self.config["debug_level"]
        self.push_config = self.config["pushbullet"]
        self.photo_timer = self.config["photo_timer"]["minutes"]
        self.keep_alive_timer = self.config["keep_alive"]["minutes"]

    def get_config(self):
        return self.config

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
            self.debug_level = new_config["debug_level"]
            self.push_config = new_config["pushbullet"]
            self.photo_timer = new_config["photo_timer"]["minutes"]
            self.keep_alive_timer = new_config["keep_alive"]["minutes"]

            self.config = new_config

            logger.info("New config loaded successfully..")
        except Exception as e:
            logger.error(f"Failed to load new config: {e}")
