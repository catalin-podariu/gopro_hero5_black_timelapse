#!/usr/bin/env python3

# This takes care of the wifi se

import time
import subprocess
import socket
import base64

from goprocam import GoProCamera, constants
from gptl_logger import logger

class GptlWifi:

    def __init__(self, wifi_config, gopro_config):
        self.wifi_config = wifi_config
        self.gopro_config = gopro_config
        self.state = "WAITING"


    def keep_alive(self, send_wol):
        logger.info("Attempting to keep GoPro Wi-Fi alive..")

        gopro_ssid = self.gopro_config["ssid"]
        if not self.ensure_wifi_connected(gopro_ssid):
            logger.warning("Cannot keep alive because we can't connect to GoPro Wi-Fi.")
            return  # We’re probably in OFFLINE_ALERT or ERROR now

        if send_wol:
            self.send_wol()
            time.sleep(3)  # short sleep to let the packet do its thing
            self.send_wol()

            if not self.check_network_reachable(self.gopro_config["ip"]):
                logger.warning("GoPro not reachable even after sending WOL. Possibly off already. But why?!")
                return

            try:
                gopro = GoProCamera.GoPro(self.gopro_config["ip"])
                logger.info(f"Connected to GoPro. {gopro}")
                gopro.power_on()
                time.sleep(2)
                gopro.mode(constants.Mode.PhotoMode)
                time.sleep(3)
            except Exception as e:
                logger.error(f"Error controlling GoPro in keep_alive: {e}")
                return

            try:
                logger.info("Coolio. Going back to sleep for now.. Still in WAITING.")
                gopro.power_off()
                time.sleep(3)
            except Exception as e:
                logger.error(f"Error powering off GoPro in keep_alive: {e}")
                return

        logger.info("keep_alive sequence completed.")

    def send_wol(self):
        mac_address = self.gopro_config["mac"]
        try:
            if len(mac_address) == 17 and mac_address.count(':') == 5:
                mac_bytes = bytes.fromhex(mac_address.replace(':', ''))
                magic_packet = b'\xff' * 6 + mac_bytes * 16

                # Send the magic packet to the broadcast address
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    sock.settimeout(3)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    sock.sendto(magic_packet, ('<broadcast>', 9))
                logger.info(f"Magic packet sent to {mac_address}")
            else:
                logger.info("Invalid MAC address format")
        except Exception as e:
            logger.error(f"Error sending WOL packet: {e}")

    def check_network_reachable(self, ip, retries=5, delay=4):
        for attempt in range(retries):
            try:
                subprocess.run(["ping", "-c", "1", ip], check=True, stdout=subprocess.DEVNULL)
                logger.info(f"Network is reachable at {ip}")
                return True
            except subprocess.CalledProcessError:
                logger.warning(f"Ping to {ip} failed. Attempt {attempt + 1}/{retries}.")
                self.restart_wifi()
                time.sleep(delay)
        logger.error(f"Network not reachable after {retries} attempts.")
        return False

    def ensure_wifi_connected(self, ssid):
        current_wifi = get_current_wifi() or ""
        if current_wifi.lower() == ssid.lower():
            logger.info(f"Already connected to {ssid}")
            return True

        logger.info(f"Connecting to Wi-Fi: {ssid}")
        if not self.switch_wifi(ssid):
            logger.error(f"Could not connect to {ssid} ->  We are in [{self.state}].")
            self.state = "OFFLINE_ALERT"
            return False

        return True

    def switch_wifi(self, target_ssid):
        pwd = self._determine_wifi_password(target_ssid)
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

    def _determine_wifi_password(self, ssid):
        if ssid == self.gopro_config["ssid"]:
            return base64.b64decode(self.gopro_config["pwd"]).decode("utf-8")
        else:
            return base64.b64decode(self.wifi_config["pwd"]).decode("utf-8")

    def restart_wifi(self):
        logger.info("Restarting Wi-Fi interface..")
        subprocess.run(["sudo", "ifdown", "wlan0"])
        time.sleep(5)
        subprocess.run(["sudo", "ifup", "wlan0"])
        time.sleep(10)
        if self.ensure_wifi_connected(self.gopro_config["ssid"]):
            logger.info("Wi-Fi reconnected successfully.")
        else:
            logger.error("Wi-Fi restart failed. Manual intervention required.")

# ------------------------------------------------------------------

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
