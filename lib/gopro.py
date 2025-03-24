#!/usr/bin/env python3

import time

from goprocam import GoProCamera, constants
from lib.logger import logger
from lib.wifi import Wifi
from lib.config import Config
from util.download_pictures import gopro_config


class GoPro:

    def __init__(self):
        self.wifi = Wifi()
        self.config = Config()
        self.gopro_config = self.config.gopro_config
        self.photo_capture_error_counter = 0


    def take_photo(self):
        try:
            logger.info("Waking up the GoPro with magic package.")
            self.wifi.send_wol(self.gopro_config["mac"])
            time.sleep(3)  # short sleep to let the packet settle
            self.wifi.send_wol(self.gopro_config["mac"])

            if not self.wifi.check_network_reachable(self.gopro_config["ip"]):
                logger.error("GoPro not reachable even after sending WOL. Possibly off already. But why?!")
                return

            self.wifi.check_network_reachable(self.gopro_config["ip"])
            logger.info("Connecting to GoPro camera..")

            gopro = GoProCamera.GoPro(self.gopro_config["ip"])
            logger.info(f"Connected to GoPro. {gopro}")
            gopro.power_on()

            logger.info("Setting camera to photo mode..")
            gopro.mode(constants.Mode.PhotoMode)
            time.sleep(2)

            logger.info("Taking photo now..")
            gopro.take_photo()
            time.sleep(5)

            logger.info("Shutting down GoPro..")
            gopro.power_off()
            time.sleep(3)

        except Exception as e:
            self.photo_capture_error_counter += 1
            raise e

    def take_video(self):
        pass

    def start_beeper(self):
        pass
