#!/usr/bin/env python3
# timelapse.py
# Orchestrates the timelapse process using separate modules from lib/.

import time
from lib.logger import logger
from lib.state import State
from lib.cycles import Cycles
from lib.config import Config

class Timelapse:

    def __init__(self):
        self.current_state = "WAITING"
        self.restart_counter = 0
        self.state = State()
        self.cycle = Cycles()
        self.config = Config()

    def main_cycle(self):
        self.state.load_state()
        logger.logo()

        """
        Runs forever, checking if it's time to take a photo (in WAITING),
        capturing photos (TAKE_PHOTO), sending updates (SEND_UPDATE),
        handling errors (ERROR) or sending alerts (OFFLINE_ALERT).
        """
        self.restart_counter += 1
        while True:
            try:
                logger.info(f"Starting main cycle. Current state = {self.current_state}")
                if self.current_state == "WAITING":
                    self.cycle.handle_waiting_state()
                elif self.current_state == "TAKE_PHOTO":
                    self.cycle.handle_take_photo_state()
                elif self.current_state == "SEND_UPDATE":
                    self.cycle.handle_send_update_state()
                elif self.current_state == "ERROR":
                    self.cycle.handle_error_state()

                # EMERGENCY STATE: If GoPro is offline, we send alert
                elif self.current_state == "OFFLINE_ALERT":
                    self.cycle.handle_offline_alert_state()
                else:
                    logger.error(f"Unknown state: {self.current_state}. Forcing ERROR.")
                    self.current_state = "ERROR"

                # Wait a few seconds before next loop
                time.sleep(10)
            except Exception as e:
                logger.error(f"Unexpected error in main cycle: {e}")
                self.current_state = "ERROR"
                time.sleep(10)

if __name__ == "__main__":
    controller = Timelapse()
    controller.main_cycle()
