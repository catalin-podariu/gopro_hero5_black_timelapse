#!/usr/bin/env python3
# timelapse.py
# Orchestrates the timelapse process using separate modules from lib/.

import time
import lib.config as config
import lib.state as state

from lib.logger import logger


class Timelapse:

    def __init__(self):
        self.config = config.global_config
        self.state_instance = state.state_instance

    def main_loop(self):
        self.config.load_saved_config()
        logger.logo()

        """
        Runs forever, checking if it's time to take a photo (in WAITING),
        capturing photos (TAKE_PHOTO), sending updates (SEND_UPDATE),
        handling errors (ERROR) or sending alerts (OFFLINE_ALERT).
        """
        self.config.restart_counter += 1
        while True:
            try:
                logger.info(f"Starting main cycle. Current state = {self.state_instance.current_state}")
                if self.state_instance.current_state == "WAITING":
                    self.state_instance.handle_waiting_state()
                elif self.state_instance.current_state == "TAKE_PHOTO":
                    self.state_instance.handle_take_photo_state()
                elif self.state_instance.current_state == "SEND_UPDATE":
                    self.state_instance.handle_send_update_state()
                elif self.state_instance.current_state == "ERROR":
                    self.state_instance.handle_error_state()

                # EMERGENCY STATE: If GoPro is offline, we send alert
                elif self.state_instance.current_state == "OFFLINE_ALERT":
                    self.state_instance.handle_offline_alert_state()
                else:
                    logger.error(f"Unknown state: {self.state_instance.current_state}. Forcing ERROR.")
                    self.state_instance.current_state = "ERROR"

                # Wait a few seconds before next loop
                time.sleep(10)
            except Exception as e:
                logger.error(f"Unexpected error in main cycle: {e}")
                self.state_instance.current_state = "ERROR"
                time.sleep(10)

if __name__ == "__main__":
    controller = Timelapse()
    controller.main_loop()
