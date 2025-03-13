#!/usr/bin/env python3

import socket
import sys
import os
import time
import json

from goprocam import GoProCamera, constants
from logger import logger

# This is using the GoPro API to download photos from a GoPro camera.
# The laptop must be connected to the GoPro camera's WiFi network.
# Then, the script will read the config.json file to get the GoPro IP address and password.
# Make sure you change the working directory in the config.json and the path here, to the directory where you want to save the photos.

# author: mrbigheart

def load_config(config_path="config.json"):
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Could not load config.json: {e}")
        sys.exit(1)

config = load_config()
gopro_config = config["gopro"]
gopro_ip = gopro_config["ip"]


def main(dir="/Users/mrbigheart/gopro_downloads/media"):
    gopro = GoProCamera.GoPro(gopro_ip)
    logger.info("Connected to GoPro. Fetching media list...")

    # ----------------------------------------------------------------------
    # NEW: Build a set of the existing local photos to skip them up front.
    # ----------------------------------------------------------------------
    try:
        local_photos = {
            f.lower()
            for f in os.listdir(dir)
            if f.lower().endswith((".jpg", ".jpeg"))
        }
    except FileNotFoundError:
        # If the directory doesn't exist, create it so we can download
        os.makedirs(dir, exist_ok=True)
        local_photos = set()

    logger.info(f"Found {len(local_photos)} photos locally. Will skip these if present on camera.")
    # ----------------------------------------------------------------------

    try:
        media_list = gopro.listMedia(format=True, media_array=True)
        if not media_list:
            logger.info("No media found on GoPro, or could not retrieve list.")
            return

        photos = []
        for item in media_list:
            folder, filename = item[0], item[1]
            # only pick up .jpg / .jpeg
            if filename.lower().endswith((".jpg", ".jpeg")):
                # ----------------------------------------------------------------------
                # Skip adding to the download list if we already have it locally
                # ----------------------------------------------------------------------
                if filename.lower() not in local_photos:
                    photos.append((folder, filename))
                # ----------------------------------------------------------------------

        logger.info(f"Found {len(photos)} new photos to download.")

        batch_size = 10
        for i in range(0, len(photos), batch_size):
            batch = photos[i : i + batch_size]
            for folder, filename in batch:
                local_path = os.path.join(dir, filename)
                if os.path.exists(local_path):
                    logger.info(f"File {filename} already exists locally, skipping.")
                    continue
                logger.info(f"Downloading {folder}/{filename} -> {local_path}")
                gopro.downloadMedia(folder, filename, custom_filename=local_path)
                time.sleep(1)
            logger.info(f"Finished batch {i//batch_size + 1}.")
            time.sleep(2)  # small pause between batches

        logger.info("All downloads complete.")
    except Exception as e:
        logger.error(f"Failed to list or download media: {e}")


if __name__ == "__main__":
    main()
