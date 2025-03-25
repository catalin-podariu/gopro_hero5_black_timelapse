#!/usr/bin/env python3
# timelapse.py
# Orchestrates the timelapse process using separate modules from lib/.

import time
import datetime

import lib.config as config
import lib.state as state

from lib.logger import logger


class Timelapse:

    def __init__(self):
        self.config = config.global_config
        self.state_handler = state.handler

    def main_loop(self):
        self.config.load_saved_config()
        logger.logo()

        """
        Runs forever, checking if it's time to take a photo (in WAITING),
        capturing photos (TAKE_PHOTO), sending updates (SEND_UPDATE),
        handling errors (ERROR) or sending alerts (OFFLINE_ALERT).
        """
        self.config.restart_counter += 1
        self.config.execution_start_time = datetime.datetime.now()
        while True:
            try:
                logger.info(f"Starting main cycle. Current state = {self.config.state}")
                if self.config.state == "WAITING":
                    self.state_handler.handle_waiting()
                elif self.config.state == "TAKE_PHOTO":
                    self.state_handler.handle_taking_photo()
                elif self.config.state == "SEND_UPDATE":
                    self.state_handler.handle_sending_update()
                elif self.config.state == "ERROR":
                    self.state_handler.handle_errors()

                # EMERGENCY STATE: If GoPro is offline, we send alert
                elif self.config.state == "OFFLINE_ALERT":
                    self.state_handler.handle_being_offline()
                else:
                    logger.error(f"Unknown state: {self.config.state}. Forcing ERROR.")
                    self.config.state = "ERROR"

                # Wait a few seconds before next loop
                time.sleep(10)
            except Exception as e:
                logger.error(f"Unexpected error in main cycle: {e}")
                self.config.state = "ERROR"
                time.sleep(10)

if __name__ == "__main__":
    controller = Timelapse()
    controller.main_loop()
