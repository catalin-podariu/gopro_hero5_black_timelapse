#!/usr/bin/env python3

import os
import time
import json
import logging
import sys
from goprocam import GoProCamera, constants
import subprocess

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Adjust as needed
CONFIG_PATH = "/home/timelapse/config.json"
DOWNLOAD_DIR = "/home/timelapse/photos"  # where to store the images


def load_config(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Could not load config.json: {e}")
        sys.exit(1)


def ensure_wifi_connected(ssid, password, retries=3, delay=5):
    """
    Simple wrapper for nmcli-based Wi-Fi connection.
    If already connected, returns True quickly. If fails, returns False.
    """
    # Check current Wi-Fi
    try:
        result = subprocess.run(["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"],
                                capture_output=True, text=True)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith("yes"):
                    current_ssid = line.split(":")[1]
                    if current_ssid.lower() == ssid.lower():
                        logging.info(f"Already connected to {ssid}")
                        return True
    except Exception as e:
        logging.error(f"Error checking current Wi-Fi: {e}")

    # Not connected, attempt nmcli connect
    for attempt in range(retries):
        try:
            cmd = f"nmcli dev wifi connect '{ssid}' password '{password}'"
            subprocess.run(cmd, shell=True, check=True)
            time.sleep(5)
            # re-check
            result = subprocess.run(["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"],
                                    capture_output=True, text=True)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.startswith("yes"):
                        current_ssid = line.split(":")[1]
                        if current_ssid.lower() == ssid.lower():
                            logging.info(f"Connected to {ssid}")
                            return True
        except subprocess.CalledProcessError as e:
            logging.warning(f"Attempt {attempt+1}/{retries} to connect {ssid} failed. {e}")
            time.sleep(delay)

    logging.error(f"Failed to connect to {ssid} after {retries} tries.")
    return False


def main():
    config = load_config(CONFIG_PATH)

    gopro_config = config["gopro"]
    ssid = gopro_config["ssid"]
    pwd = gopro_config["pwd"]
    gopro_ip = gopro_config["ip"]

    if not ensure_wifi_connected(ssid, pwd):
        logging.error(f"Cannot proceed without connecting to GoPro Wi-Fi: {ssid}")
        sys.exit(1)

    # Create download directory if needed
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

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
                local_path = os.path.join(DOWNLOAD_DIR, filename)
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
