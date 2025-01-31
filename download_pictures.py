#!/usr/bin/env python3

import socket
import sys
import os
import time
import json

from goprocam import GoProCamera, constants
from logger import logger

def load_config(config_path="config.json"):
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Could not load config.json: {e}")
        sys.exit(1)

config = load_config()
gopro_config = config["gopro"]
ssid = gopro_config["ssid"]
pwd = gopro_config["pwd"]
gopro_ip = gopro_config["ip"]


def main(dir="~/workspace/personal/code/gopro_downloads"):

    # Connect to GoPro
    gopro = GoProCamera.GoPro(gopro_ip)
    logger.info("Connected to GoPro. Fetching media list...")

    try:
        media_list = gopro.listMedia(format=True, media_array=True)
        if not media_list:
            logger.info("No media found on GoPro, or could not retrieve list.")
            return

        # media_list is typically a list of tuples: [ (folder, filename), ... ]
        photos = []
        for item in media_list:
            folder, filename = item[0], item[1]
            if filename.lower().endswith((".jpg", ".jpeg")):
                photos.append((folder, filename))

        logger.info(f"Found {len(photos)} photos to download.")

        # Download in batches of 10
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

def send_wol(self):
    mac_address = self.gopro_config["mac"]
    try:
        if len(mac_address) == 17 and mac_address.count(':') == 5:
            mac_bytes = bytes.fromhex(mac_address.replace(':', ''))
            magic_packet = b'\xff' * 6 + mac_bytes * 16

            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(3)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.sendto(magic_packet, ('<broadcast>', 9))
            logger.info(f"Magic packet sent to {mac_address}")
        else:
            logger.info("Invalid MAC address format")
    except Exception as e:
        logger.error(f"Error sending WOL packet: {e}")

if __name__ == "__main__":
    main()
