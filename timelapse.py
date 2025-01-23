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

        self.config_path = config_path
        with open(config_path, "r") as f:
            self.config = json.load(f)

        # Default is WAITING
        self.state = "WAITING"
        # 'state' is NOT saved in state.json
        self.state_path = "state.json"

        self.wifi_config = self.config["wifi"]
        self.gopro_config = self.config["gopro"]
        self.push_config = self.config["pushbullet"]
        self.photo_timer = self.config["photo_timer"]["minutes"]
        self.watchdog_timer = self.config["watchdog_timer"]["milliseconds"]

        self.wdt = WatchdogTimer(timeout=self.watchdog_timer)
        self.debug_level = None

        self.gopro_offline_user_notified = False
        self.last_offline_alert_time = None
        self.last_photo_minute = None
        self.last_keep_alive_time = datetime.datetime.now()
        self.execution_start_time = datetime.datetime.now()

        self.photo_number = 0
        self.wifi_retry_counter = 0
        self.reach_for_help_counter = 0
        self.photo_capture_error_counter = 0

        self.error_retries = 0
        self.max_error_retries = 5

        signal.signal(signal.SIGINT, self.handle_sigint)
        atexit.register(self.on_exit)

    # ------------------------------------------------------------------

    def main_cycle(self):
        logger.logo()
        """
        Runs forever, checking if it's time to take a photo (in WAITING),
        capturing photos (TAKE_PHOTO), sending updates (SEND_UPDATE),
        handling errors (ERROR) or sending alerts (OFFLINE_ALERT).
        """
        while True:
            try:
                logger.info(f"Starting main cycle. Current state = {self.state}")
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
                time.sleep(10)
            except Exception as e:
                logger.error(f"Unexpected error in main cycle: {e}")
                self.state = "ERROR"
                time.sleep(10)

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
            logger.error(f"Failed to connect to GoPro Wi-Fi. We are in [{self.state}].")
            # self.state = "ERROR"
            return

        # 2. Actually take the photo
        try:
            self.take_photo()
            self.last_photo_minute = datetime.datetime.now().minute
            self.last_keep_alive_time = datetime.datetime.now()

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
        elif self.photo_capture_error_counter > 3:
            logger.error("Too many photo capture errors. Will attempt to recover by returning to WAITING.")
            self.state = "OFFLINE_ALERT"
        else:
            logger.error("Exceeded max error retries. Considering a forced reboot or state reset.")
            # o
            # subprocess.run(["sudo", "reboot"])

            self.state = "WAITING"
            self.error_retries = 0

    def handle_offline_alert_state(self):
        """
        Repeatedly tries to connect to router Wi-Fi,
        then attempts GoPro Wi-Fi. If both fail, remains offline.

        - Send one immediate 'GoPro offline' notification if this is the first time.
        - Then send repeated notifications every 20 minutes if it remains offline.
        """
        router_ssid = self.wifi_config["ssid"]
        now = datetime.datetime.now()

        if not hasattr(self, "last_offline_alert_time"):
            self.last_offline_alert_time = now - datetime.timedelta(hours=1)

        # 1) Attempt to connect to router
        if self.ensure_wifi_connected(router_ssid):
            # Router is OK, try the GoPro
            self.last_offline_alert_time = now

            gopro_ssid = self.gopro_config["ssid"]
            if self.ensure_wifi_connected(gopro_ssid):
                # Full recovery: both router & GoPro are up
                logger.info("Router & GoPro reconnected. Returning to WAITING.")
                self.gopro_offline_user_notified = False  # reset
                self.state = "WAITING"
            else:
                # We can't reach GoPro, but router is fine
                if not self.gopro_offline_user_notified:
                    # Send an immediate, one-time alert
                    self.send_notification(
                        "GoPro OFFLINE!",
                        "\nRouter is OK, but I CANNOT connect to GoPro. [First-time alert.]"
                    )
                    self.gopro_offline_user_notified = True
                    self.last_offline_alert_time = now
                else:
                    # Already sent the first-time alert; see if 20 min has passed
                    time_since_alert = now - self.last_offline_alert_time
                    if time_since_alert.total_seconds() >= 1200:  # 20 minutes
                        self.send_notification(
                            "GoPro OFFLINE!",
                            "\nRouter is OK, but STILL CAN NOT connect to GoPro. [20 min repeat]"
                        )
                        self.last_offline_alert_time = now

        else:
            # Router is offline too, or we can't connect.
            # most likely we reboot the whole rpi here.
            logger.warning("Router is offline as well; can't do a push. Remain in OFFLINE_ALERT.")


    # ------------------------------------------------------------------

    def ensure_wifi_connected(self, ssid):
        current_wifi = self.get_current_wifi() or ""
        if current_wifi.lower() == ssid.lower():
            logger.info(f"Already connected to {ssid}")
            return True

        logger.info(f"Connecting to Wi-Fi: {ssid} ...")
        if not self.switch_wifi(ssid):
            logger.error(f"Could not connect to {ssid} ->  We are in [{self.state}].")
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
                logger.warning(f"nmcli connect attempt failed. SSID not found or password is incorrect.")
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

        # Send WOL every 4 minutes
        if (datetime.datetime.now() - self.last_keep_alive_time).total_seconds() >= 240:
            self.last_keep_alive_time = datetime.datetime.now()
            self.send_wol()
            time.sleep(2)  # short sleep to let the packet go out

            # 3) Check network
            if not self.check_network_reachable(self.gopro_config["ip"]):
                logger.warning("GoPro not reachable even after WOL. Possibly off or out of range.")
                return

            try:
                gopro = GoProCamera.GoPro(self.gopro_config["ip"])
                logger.info(f"Connected to GoPro. {gopro}")
                gopro.mode(constants.Mode.PhotoMode)
                time.sleep(2)
            except Exception as e:
                logger.error(f"Error controlling GoPro in keep_alive: {e}")
                return

            try:
                logger.info("Coolio. Going back to sleep for now...")
                gopro.power_off()
                time.sleep(2)
            except Exception as e:
                logger.error(f"Error powering off GoPro in keep_alive: {e}")
                return

        logger.info("keep_alive sequence completed.")

    def take_photo(self):
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
        url = "https://api.pushbullet.com/v2/pushes"
        headers = {
            "Access-Token": self.push_config["api_key"],
            "Content-Type": "application/json"
        }
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        data = {
            "type": "note",
            "title": "Time-lapse update",
            "body": f"{timestamp} - Photo count = {self.photo_number}. \nTemp is [{self.rpi_temp()}]. \nAll iz good.."
        }
        try:
            resp = requests.post(url, headers=headers, json=data)
            if resp.status_code == 200:
                logger.info(f"Push notification sent successfully -- [STATUS] {timestamp} -- {data}")
            else:
                logger.error(f"This is PushBullet's error: {resp.status_code}, {resp.text}")
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

    def reload_config(self):
        """
        Re-read 'config.json' from disk and update all relevant fields
        (wifi_config, gopro_config, rpi, push_config, photo_timer, etc.).
        """
        try:
            with open(self.config_path, "r") as f:
                new_config = json.load(f)

            # Update everything you need
            self.wifi_config = new_config["wifi"]
            self.gopro_config = new_config["gopro"]

            self.push_config = new_config["pushbullet"]
            self.photo_timer = new_config["photo_timer"]["minutes"]

            self.watchdog_timer = new_config["watchdog_timer"]["milliseconds"]
            # If you want to re-instantiate the WatchdogTimer with new time:
            # self.wdt = WatchdogTimer(timeout=self.watchdog_timer)

            self.debug_level = new_config["debug_level"]

            self.config = new_config

            logger.info("NEW config reloaded successfully..")
        except Exception as e:
            logger.error(f"Failed to reload config: {e}")


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
            "photo_number": self.photo_number if self.photo_number else 0,
            "last_photo_minute": self.last_photo_minute if self.last_photo_minute else None,
            "last_offline_alert_time": self.last_offline_alert_time if self.last_offline_alert_time else None,
            "photo_capture_error_counter": self.photo_capture_error_counter if self.photo_capture_error_counter else 0,
            "reach_for_help_counter": self.reach_for_help_counter if self.reach_for_help_counter else 0,
            "error_retries": self.error_retries if self.error_retries else 0,
            "max_error_retries": self.max_error_retries if self.max_error_retries else 5,
            "execution_time_seconds": (datetime.datetime.now() - self.execution_start_time).total_seconds(),
        }
        try:
            with open(self.state_path, "w") as f:
                json.dump(data, f, indent=4)
            logger.info(f"Saved state to {self.state_path}.")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def fromisoformat_fallback(self, iso_string): # Python 3.6 compatibility
        return datetime.datetime.strptime(iso_string, "%Y-%m-%dT%H:%M:%S")

    def rpi_temp(self):
        try:
            temp = subprocess.run(["vcgencmd", "measure_temp"], capture_output=True, text=True)
            if temp.returncode == 0:
                temp_value = float(temp.stdout.strip().split('=')[1].replace("'C", ""))
                return f"NORMAL - {temp_value}" if temp_value < 60.0 else f"HIGH - {temp_value}"
            else:
                return "UNKNOWN"
        except Exception:
            return "UNKNOWN"

    def on_exit(self):
        self.save_state()
        logger.info(f"Script ran for {(datetime.datetime.now() - self.execution_start_time).total_seconds()} seconds.")
        logger.info("Script is shutting down. Saving state...")

    def handle_sigint(self, signal_received, frame):
        logger.info("Ctrl+C received. Exiting gracefully...")
        sys.exit(0)

# ------------------------------------------------------------------

if __name__ == "__main__":
    controller = TimelapseController("config.json")
    controller.main_cycle()
