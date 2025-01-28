#!/usr/bin/env python3

import os
import time
import json
import logging
import sys
import subprocess
from goprocam import GoProCamera, constants
from logger import logger

def load_config(config_path="config.json"):
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Could not load config.json: {e}")
        sys.exit(1)

config = load_config()
gopro_config = config["gopro"]
ssid = gopro_config["ssid"]
pwd = gopro_config["pwd"]
gopro_ip = gopro_config["ip"]

def ensure_wifi_connected(self, ssid):
    current_wifi = self.get_current_wifi() or ""
    if current_wifi.lower() == ssid.lower():
        logger.info(f"Already connected to {ssid}")
        return True

    logger.info(f"Connecting to Wi-Fi: {ssid}")
    if not self.switch_wifi(ssid):
        logger.error(f"Could not connect to {ssid} ->  We are in [{self.state}].")
        self.state = "OFFLINE_ALERT"
        return False

    return True

def get_current_wifi():
    try:
        result = subprocess.run(["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"],
                                capture_output=True, text=True)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith("yes"):
                    return line.split(":")[1]
        return None
    except Exception as e:
        logger.error(f"Failed to get current wifi: x")
        return None

def switch_wifi(target_ssid):
    pwd = _determine_wifi_password(target_ssid)
    max_tries = 5
    for attempt in range(max_tries):
        logger.info(f"Trying to connect to {target_ssid}, attempt {attempt + 1}/{max_tries}")
        try:
            cmd = f"nmcli dev wifi connect '{target_ssid}' password '{pwd}'"
            subprocess.run(cmd, shell=True, check=True)
            time.sleep(5)  # wait for wifi to settle
            if (get_current_wifi() or "").lower() == target_ssid.lower():
                logger.info(f"Connected to {target_ssid} successfully.")
                return True
        except subprocess.CalledProcessError as e:
            logger.warning(f"nmcli connect attempt failed. SSID not found or password is incorrect. Message x")
            time.sleep(3)

    logger.error(f"Failed to connect to {target_ssid} after {max_tries} tries.")
    return False

def _determine_wifi_password(ssid):
    if ssid == gopro_config["ssid"]:
        return gopro_config["pwd"]
    else:
        logger.error(f"Unknown Wi-Fi network: {ssid}")

def main(dir="~/workspace/personal/code/gopro_downloads"):
    if not ensure_wifi_connected(ssid, pwd):
        logging.error(f"Cannot proceed without connecting to GoPro Wi-Fi: {ssid}")
        sys.exit(1)

    # Create download directory if needed
    if not os.path.exists(dir):
        os.makedirs(dir)

    # Connect to GoPro
    gopro = GoProCamera.GoPro(gopro_ip)
    logging.info("Connected to GoPro. Fetching media list...")

    try:
        media_list = gopro.listMedia(format=True, media_array=True)
        if not media_list:
            logging.info("No media found on GoPro, or could not retrieve list.")
            return

        # media_list is typically a list of tuples: [ (folder, filename), ... ]
        photos = []
        for item in media_list:
            folder, filename = item[0], item[1]
            if filename.lower().endswith((".jpg", ".jpeg")):
                photos.append((folder, filename))

        logging.info(f"Found {len(photos)} photos to download.")

        # Download in batches of 10
        batch_size = 10
        for i in range(0, len(photos), batch_size):
            batch = photos[i : i + batch_size]
            for folder, filename in batch:
                local_path = os.path.join(dir, filename)
                if os.path.exists(local_path):
                    logging.info(f"File {filename} already exists locally, skipping.")
                    continue
                logging.info(f"Downloading {folder}/{filename} -> {local_path}")
                # GoPro library might have a dedicated download method
                # using goprocam: gopro.downloadMedia(folder, filename, custom_filename=...)
                # But let's assume we do this:
                gopro.downloadMedia(folder, filename, custom_filename=local_path)
                time.sleep(1)
            logging.info(f"Finished batch {i//batch_size + 1}.")
            time.sleep(2)  # small pause between batches

        logging.info("All downloads complete.")
    except Exception as e:
        logging.error(f"Failed to list or download media: {e}")



if __name__ == "__main__":
    main()
