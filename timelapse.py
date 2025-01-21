import socket
import json
import time
import subprocess
import requests
import datetime
import atexit
import signal
import sys
from watchdog import WatchdogTimer
from logger import logger
from goprocam import GoProCamera, constants


class TimelapseController:
    def __init__(self, config_path="config.json"):

        with open(config_path, "r") as f:
            self.config = json.load(f)

        # Basic config
        self.wifi_config = self.config["wifi"]
        self.gopro_config = self.config["gopro"]
        self.push_config = self.config["pushbullet"]

        self.photo_timer = self.config["photo_timer"]["minutes"]
        self.state_path = self.config["state"]["path"]
        self.watchdog_timer = self.config["watchdog_timer"]["milliseconds"]

        self.wdt = WatchdogTimer(timeout=self.watchdog_timer)

        # States might be: WAITING, TAKE_PHOTO, SEND_UPDATE, ERROR, OFFLINE_ALERT
        self.state = "WAITING"

        self.last_offline_alert_time = None
        self.last_keep_alive_time = datetime.datetime.now()
        self.wifi_retry_counter = 0
        self.max_retries = 3
        self.reach_for_help_counter = 0
        self.keep_alive_counter = 1 # Start at 1 to avoid immediate keep_alive
        self.photo_capture_error_counter = 0
        self.photo_number = 0

        self.last_photo_minute = None

        self.error_retries = 0
        self.max_error_retries = 5

        signal.signal(signal.SIGINT, self.handle_sigint)
        atexit.register(self.on_exit)

    # ------------------------------------------------------------------
    # Main cycle: simpler approach
    # ------------------------------------------------------------------
    def main_cycle(self):
        """
        Runs forever, checking if it's time to take a photo (in WAITING),
        capturing photos (TAKE_PHOTO), sending updates (SEND_UPDATE),
        handling errors (ERROR) or sending alerts (OFFLINE_ALERT).
        """
        while True:
            try:
                logger.info(f"[main_cycle] Current state = {self.state}")
                if self.state == "WAITING":
                    self.handle_waiting_state()
                elif self.state == "TAKE_PHOTO":
                    self.handle_take_photo_state()
                elif self.state == "SEND_UPDATE":
                    self.handle_send_update_state()
                elif self.state == "ERROR":
                    self.handle_error_state()

                # EMERGENCY STATE: If GoPro is offline, we send alert
                elif self.state == "OFFLINE_ALERT":
                    self.handle_offline_alert_state()

                else:
                    logger.error(f"Unknown state: {self.state}. Forcing ERROR.")
                    self.state = "ERROR"

                # Wait a few seconds before next loop
                time.sleep(5)

            except Exception as e:
                logger.error(f"Unexpected error in main cycle: {e}")
                self.state = "ERROR"
                time.sleep(10)

    # ------------------------------------------------------------------
    #  State Handlers
    # ------------------------------------------------------------------
    def handle_waiting_state(self):
        now = datetime.datetime.now()
        hour = now.hour
        minute = now.minute
        second = now.second

        # Daily time sync at 00:05
        if hour == 0 and minute == 5 and second < 30:
            self.sync_time()

        # Photo check
        if minute in self.photo_timer and second < 30:
            if self.last_photo_minute != minute:
                logger.info("It's time to take a photo. Transitioning to TAKE_PHOTO.")
                self.state = "TAKE_PHOTO"
            else:
                logger.debug("Already took a photo this minute. Doing nothing.")
        else:
            # If not photo time, do a quick keep_alive attempt
            self.keep_alive()
            logger.debug("Not photo time. Staying in WAITING.")


    def handle_take_photo_state(self):
        """
        Switch to the GoPro Wi-Fi if needed, take the photo.
        If success, go to SEND_UPDATE. If failed, go to ERROR.
        """
        # 1. Ensure we're on GoPro Wi-Fi
        gopro_ssid = self.gopro_config["ssid"]
        if not self.ensure_wifi_connected(gopro_ssid):
            # If we can’t connect to GoPro Wi-Fi, error out
            logger.error("Failed to connect to GoPro Wi-Fi. Going to OFFLINE_ALERT.")
            # self.state = "ERROR"
            return

        # 2. Actually take the photo
        try:
            self.take_photo()
            self.last_photo_minute = datetime.datetime.now().minute

            # 3. On success, proceed to SEND_UPDATE
            self.state = "SEND_UPDATE"
        except Exception as e:
            logger.error(f"Error taking photo: {e}")
            self.photo_capture_error_counter += 1
            self.state = "ERROR"

    def handle_send_update_state(self):
        """
        Switch to router Wi-Fi, time sync, send status, save state,
        then switch back to GoPro Wi-Fi to keep it alive. Return to WAITING when done.
        """
        router_ssid = self.wifi_config["ssid"]

        if not self.ensure_wifi_connected(router_ssid):
            logger.error("Failed to connect to router Wi-Fi. ERROR.")
            self.state = "ERROR"
            return

        self.sync_time()
        self.send_status()
        self.save_state()

        gopro_ssid = self.gopro_config["ssid"]
        if not self.ensure_wifi_connected(gopro_ssid):
            logger.error("Failed to reconnect to GoPro after sending status. ERROR.")
            self.state = "ERROR"
            return

        logger.info("Update complete. Returning to WAITING.")
        self.state = "WAITING"

    def handle_error_state(self):
        """
          - We increment error_retries. If < max_error_retries, try re-init or re-connect.
          - If that fails too many times, we reboot the r-pi.
        """
        self.error_retries += 1
        logger.error(f"Error State reached. Retry attempt {self.error_retries} / {self.max_error_retries}.")

        if self.error_retries < self.max_error_retries:
            logger.info("Will attempt to recover by returning to WAITING.")
            self.state = "WAITING"
        elif photo_capture_error_counter > 3:
            logger.error("Too many photo capture errors. Will attempt to recover by returning to WAITING.")
            self.state = "OFFLINE_ALERT"
        else:
            logger.error("Exceeded max error retries. Considering a forced reboot or state reset.")
            # o
            # subprocess.run(["sudo", "reboot"])

            if os.path.exists(self.state_path):
                os.remove(self.state_path)
                logger.info("Deleted state.json. Force re-init next time.")
            self.state = "WAITING"
            self.error_retries = 0

    def handle_offline_alert_state(self):
        """
        Repeatedly tries to connect to router Wi-Fi.
        If that works, then attempts to connect to the GoPro Wi-Fi too.

        - If both succeed, reset to WAITING.
        - Otherwise, remain in OFFLINE_ALERT.

        Send an hourly push notification if GoPro is still offline.
        """
        router_ssid = self.wifi_config["ssid"]
        now = datetime.datetime.now()

        if not hasattr(self, "last_offline_alert_time"):
            self.last_offline_alert_time = now - datetime.timedelta(hours=1)

        # 1) Attempt to connect to router
        if self.ensure_wifi_connected(router_ssid):
            self.send_notification("Router back online", "It appears we have internet now..")
            self.last_offline_alert_time = now

            # 2) Now try connecting to the GoPro
            gopro_ssid = self.gopro_config["ssid"]
            if self.ensure_wifi_connected(gopro_ssid):
                # If we can also connect to the GoPro Wi-Fi, we consider state fully recovered
                self.state = "WAITING"
            else:
                self.send_notification(
                    "GoPro OFFLINE",
                    "Router is OK, but can't connect to GoPro Wi-Fi. Still OFFLINE_ALERT."
                )

        else:
            # If we couldn't connect to the router, check if we should send a "still offline" alert
            time_since_alert = now - self.last_offline_alert_time
            # TODO: Replace 240 with 3600 (one hour) in production
            if time_since_alert.total_seconds() >= 240:
                self.send_notification("Still offline", "We remain offline. Intervention required!")
                self.last_offline_alert_time = now

            logger.warning("Still offline. Will retry in main loop.")


    # ------------------------------------------------------------------


    def ensure_wifi_connected(self, ssid):
        current_wifi = self.get_current_wifi() or ""
        if current_wifi.lower() == ssid.lower():
            logger.info(f"Already connected to {ssid}")
            return True

        logger.info(f"Connecting to Wi-Fi: {ssid} ...")
        if not self.switch_wifi(ssid):
            logger.error(f"Could not connect to {ssid} -> going to OFFLINE_ALERT.")
            self.state = "OFFLINE_ALERT"
            return False

        return True

    def get_current_wifi(self):
        try:
            result = subprocess.run(["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"],
                                    capture_output=True, text=True)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.startswith("yes"):
                        return line.split(":")[1]
            return None
        except Exception as e:
            logger.error(f"Failed to get current Wi-Fi: {e}")
            return None

    def switch_wifi(self, target_ssid):
        pwd = self._determine_wifi_password(target_ssid)
        max_tries = 5
        for attempt in range(max_tries):
            logger.info(f"Trying to connect to {target_ssid}, attempt {attempt+1}/{max_tries}")
            try:
                cmd = f"nmcli dev wifi connect '{target_ssid}' password '{pwd}'"
                subprocess.run(cmd, shell=True, check=True)
                time.sleep(5)  # wait for wifi to settle
                if (self.get_current_wifi() or "").lower() == target_ssid.lower():
                    logger.info(f"Connected to {target_ssid} successfully.")
                    return True
            except subprocess.CalledProcessError as e:
                logger.warning(f"nmcli connect attempt failed: {e}")
                time.sleep(3)

        logger.error(f"Failed to connect to {target_ssid} after {max_tries} tries.")
        return False

    def _determine_wifi_password(self, ssid):
        if ssid == self.gopro_config["ssid"]:
            return self.gopro_config["pwd"]
        else:
            return self.wifi_config["pwd"]

    def keep_alive(self):
        logger.info("Attempting to keep GoPro Wi-Fi alive...")

        gopro_ssid = self.gopro_config["ssid"]
        if not self.ensure_wifi_connected(gopro_ssid):
            logger.warning("Cannot keep alive because we can't connect to GoPro Wi-Fi.")
            return  # We’re probably in OFFLINE_ALERT or ERROR now

        logger.info("keep_alive sequence completed.")
        logger.info(f"keep_alive counter {self.keep_alive_counter}")


    def take_photo(self):
        """
        Actually power up the GoPro, set photo mode, take a picture, power down, etc.
        """
        try:
            logger.info("Waking up the GoPro with Magic package.")
            self.send_wol()
            time.sleep(2)

            # Connect to camera
            self.check_network_reachable(self.gopro_config["ip"])
            logger.info("Connecting to GoPro camera...")

            gopro = GoProCamera.GoPro(self.gopro_config["ip"])
            logger.info(f"Connected to GoPro. {gopro}")

            logger.info("Setting camera to photo mode...")
            gopro.mode(constants.Mode.PhotoMode)
            time.sleep(2)

            photo_num_before = self.get_current_photo_number()
            logger.info(f"Current GoPro pictures: {photo_num_before}")

            # Actually take photo
            logger.info("Taking photo now...")
            gopro.take_photo()
            time.sleep(5)

            photo_num_after = self.get_current_photo_number()
            self.photo_number = photo_num_after
            logger.info(f"Photo captured. Photo count is now {photo_num_after}.")

            logger.info("Shutting down GoPro..")
            gopro.power_off()
            time.sleep(3)

        except Exception as e:
            self.photo_capture_error_counter += 1
            raise e

    def get_current_photo_number(self):
        """
            Check how many .jpg files exist on the GoPro. This can be expensive!
        """
        try:
            gopro = GoProCamera.GoPro(self.gopro_config["ip"])
            time.sleep(2)
            media_list = gopro.listMedia(format=True, media_array=True)
            if not media_list:
                logger.info("Media list empty or cannot retrieve.")
                return 0
            picture_count = sum(
                1 for folder in media_list if folder[1].lower().endswith(('.jpg', '.jpeg'))
            )
            return picture_count
        except Exception as e:
            logger.error(f"Could not get GoPro media count: {e}")
            return -1

    def send_status(self):
        # logger.error(f"[STATUS] {title}: {message}") TODO ADD THIS!
        url = "https://api.pushbullet.com/v2/pushes"
        headers = {
            "Access-Token": self.push_config["api_key"],
            "Content-Type": "application/json"
        }
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        data = {
            "type": "note",
            "title": "GoPro status update",
            "body": f"{timestamp} - Photo count = {self.photo_number}. All good."
        }
        try:
            resp = requests.post(url, headers=headers, json=data)
            if resp.status_code == 200:
                logger.info("Status push notification sent successfully.")
            else:
                logger.error(f"PushBullet error: {resp.status_code}, {resp.text}")
        except Exception as e:
            logger.error(f"Error sending status: {e}")

    def send_notification(self, title, message):
        logger.error(f"[ALERT] {title}: {message}")
        try:
            url = "https://api.pushbullet.com/v2/pushes"
            headers = {
                "Access-Token": self.push_config["api_key"],
                "Content-Type": "application/json"
            }
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            data = {
                "type": "note",
                "title": title,
                "body": f"[{timestamp}] -- {message}"
            }
            resp = requests.post(url, headers=headers, json=data)
            if resp.status_code == 200:
                logger.info("Push notification sent..")
            else:
                logger.error(f"Pushbullet error: {resp.status_code} -> {resp.text}")
        except Exception as e:
            logger.error(f"Error sending pushbullet: {e}")


    def sync_time(self):
        try:
            logger.info("Syncing time via ntpdate...")
            subprocess.run(["sudo", "ntpdate", "-u", "pool.ntp.org"], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            logger.info("Time sync successful.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Time sync failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in time sync: {e}")

    def check_network_reachable(self, ip, retries=5, delay=4):
        for attempt in range(retries):
            try:
                subprocess.run(["ping", "-c", "1", ip], check=True, stdout=subprocess.DEVNULL)
                logger.info(f"Network is reachable at {ip}")
                return True
            except subprocess.CalledProcessError:
                logger.warning(f"Ping to {ip} failed. Attempt {attempt+1}/{retries}.")
                time.sleep(delay)
        logger.error(f"Network not reachable after {retries} attempts.")
        return False

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

    def load_state(self):
        try:
            with open(self.state_path, "r") as f:
                state_data = json.load(f)

            # Convert string timestamps back to datetime objects
            for key in ["last_photo_minute", "last_offline_alert_time"]:
                if key in state_data:
                    state_data[key] = self.fromisoformat_fallback(state_data[key])
            return state_data
        except FileNotFoundError as e:
            logger.error(f"Error loading state file: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error loading state: {e}")
            return {}

    def save_state(self):
        data = {
            # "state": self.state, # Do you want to resume in the same state?
            "photo_number": self.photo_number,
            "last_photo_minute": self.last_photo_minute,
            "last_offline_alert_time": self.last_offline_alert_time,
            "photo_capture_error_counter": self.photo_capture_error_counter,
            "reach_for_help_counter": self.reach_for_help_counter,
            "error_retries": self.error_retries,
            "max_error_retries": self.max_error_retries,
        }
        try:
            with open(self.state_path, "w") as f:
                json.dump(data, f, indent=4)
            logger.info(f"Saved state to {self.state_path}.")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def fromisoformat_fallback(self, iso_string): # Python 3.6 compatibility
        return datetime.datetime.strptime(iso_string, "%Y-%m-%dT%H:%M:%S")

    def on_exit(self):
        self.save_state()
        logger.info("Script is shutting down. Saving state...")

    def handle_sigint(self, signal_received, frame):
        logger.info("Ctrl+C received. Exiting gracefully...")
        sys.exit(0)


if __name__ == "__main__":
    controller = TimelapseController("config.json")
    controller.main_cycle()
