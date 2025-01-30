#!/usr/bin/env python3

import time

from gptl_wifi import GptlWifi
from goprocam import GoProCamera, constants
from gptl_logger import logger


class GptlGopro:
    def __init__(self, gopro_config):
        self.gopro_config = gopro_config
        self.photo_capture_error_counter = 0
        self.wifi = GptlWifi(self.gopro_config["router"], self.gopro_config)

    def take_photo(self):
        try:
            logger.info("Waking up the GoPro with Magic package.")

            time.sleep(2)

            # Connect to camera
            self.wifi.check_network_reachable(self.gopro_config["ip"])
            logger.info("Connecting to GoPro camera..")

            gopro = GoProCamera.GoPro(self.gopro_config["ip"])
            logger.info(f"Connected to GoPro. {gopro}")
            gopro.power_on()

            logger.info("Setting camera to photo mode..")
            gopro.mode(constants.Mode.PhotoMode)
            time.sleep(2)

            # Actually taking the photo
            logger.info("Taking photo now..")
            gopro.take_photo()
            time.sleep(5)

            logger.info("Shutting down GoPro..")
            gopro.power_off()
            time.sleep(3)

        except Exception as e:
            self.photo_capture_error_counter += 1
            raise e

    # todo: implement these at some point
    def take_video(self):
        pass

    def start_beeper(self):
        pass