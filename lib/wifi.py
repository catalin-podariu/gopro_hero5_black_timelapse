#!/usr/bin/env python3

import base64
import subprocess
import time
import socket
import lib.config as config

from goprocam import GoProCamera, constants
from lib.logger import logger


class Wifi:

    def __init__(self):
        self.config = config.global_config

    def check_network_reachable(self, ip, retries=5, delay=4):
        for attempt in range(retries):
            try:
                subprocess.run(["ping", "-c", "1", ip], check=True, stdout=subprocess.DEVNULL)
                logger.info(f"Network is reachable at {ip}")
                return True
            except subprocess.CalledProcessError:
                logger.warning(f"Ping to {ip} failed. Attempt {attempt + 1}/{retries}.")
                if attempt == 5:
                    self.restart_wifi()
                time.sleep(delay)
        logger.error(f"Network not reachable after {retries} attempts.")
        return False

    def ensure_wifi_connected(self, ssid):
        current_wifi = self.get_current_wifi() or ""
        if current_wifi.lower() == ssid.lower():
            logger.info(f"Already connected to {ssid}")
            return True

        logger.info(f"Connecting to Wi-Fi: {ssid}")
        if not self.switch_wifi(ssid):
            config.global_config.state = "OFFLINE_ALERT"
            logger.error(f"Could not connect to {ssid} ->  We are in [{config.global_config.state}].")
            return False
        return True

    def switch_wifi(self, target_ssid):
        pwd = self.choose_wifi_password(target_ssid)
        max_tries = 5
        for attempt in range(max_tries):
            logger.info(f"Trying to connect to {target_ssid}, attempt {attempt + 1}/{max_tries}")
            try:
                cmd = f"sudo nmcli dev wifi connect '{target_ssid}' password '{pwd}'"
                subprocess.run(cmd, shell=True, check=True)
                time.sleep(5)  # wait for wi-fi to settle
                if (self.get_current_wifi() or "").lower() == target_ssid.lower():
                    logger.info(f"Connected to {target_ssid} successfully.")
                    return True
            except subprocess.CalledProcessError as e:
                logger.warning(f"sudo nmcli connect attempt failed. SSID not found or password is incorrect. Message: {e}")
                logger.debug(f"ssid: {target_ssid}, pwd: {pwd}")
                time.sleep(3)

        logger.error(f"Failed to connect to {target_ssid} after {max_tries} tries.")
        return False

    def restart_wifi(self):
        logger.info("Restarting Wi-Fi interface..")
        subprocess.run(["sudo", "ifdown", "wlan0"])
        time.sleep(5)
        subprocess.run(["sudo", "ifup", "wlan0"])
        time.sleep(10)
        if self.ensure_wifi_connected(self.config.gopro_config["ssid"]):
            logger.info("Wi-Fi reconnected successfully.")
        else:
            logger.error("Wi-Fi restart failed. Manual intervention required.")

    def keep_alive(self, send_wol):
        logger.info("Attempting to keep GoPro Wi-Fi alive..")

        gopro_ssid = self.config.gopro_config["ssid"]
        if not self.ensure_wifi_connected(gopro_ssid):
            logger.warning("Cannot keep alive because we can't connect to GoPro Wi-Fi.")
            return  # We’re probably in OFFLINE_ALERT or ERROR now

        if send_wol:
            self.send_wol(self.config.gopro_config["mac"])
            time.sleep(3)  # short sleep to let the packet settle
            self.send_wol(self.config.gopro_config["mac"])

            if not self.check_network_reachable(self.config.gopro_config["ip"]):
                logger.error("GoPro not reachable even after sending WOL. Possibly off already. But why?!")
                return

            try:
                gopro = GoProCamera.GoPro(self.config.gopro_config["ip"])
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

    def send_wol(self, mac_address):
        try:
            if len(mac_address) == 17 and mac_address.count(':') == 5:
                mac_bytes = bytes.fromhex(mac_address.replace(':', ''))
                magic_packet = b'\xff' * 6 + mac_bytes * 16

                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    sock.settimeout(3)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    sock.sendto(magic_packet, ('<broadcast>', 9))
                logger.info(f"WOL Magic packet sent to {mac_address}")
            else:
                logger.info("Invalid MAC address format")
        except Exception as e:
            logger.error(f"Error sending WOL packet: {e}")

    def choose_wifi_password(self, ssid):
        if ssid == self.config.gopro_config["ssid"]:
            return base64.b64decode(self.config.gopro_config["pwd"]).decode("utf-8")
        elif ssid == self.config.router_config["ssid"]:
            return base64.b64decode(self.config.router_config["pwd"]).decode("utf-8")

    def get_current_wifi(self):
        try:
            result = subprocess.run(["sudo", "nmcli", "-t", "-f", "active,ssid", "dev", "wifi"],
                                    capture_output=True, text=True)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.startswith("yes"):
                        return line.split(":")[1]
            return None
        except Exception as ex:
            logger.error(f"Failed to get current wifi: x", ex)
            return None

wifi = Wifi()
