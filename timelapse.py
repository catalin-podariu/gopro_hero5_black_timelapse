import atexit
import datetime
import json
import requests
import signal
import socket
import subprocess
import sys
import time
from goprocam import GoProCamera, constants

from logger import logger


class TimelapseController:
    def __init__(self, config_path="config.json"):

        self.config_path = config_path
        with open(config_path, "r") as f:
            self.config = json.load(f)

        self.state = "WAITING" # default value
        # 'state' is NOT saved in state.json
        self.state_path = "state.json"

        self.wifi_config = self.config["wifi"]
        self.gopro_config = self.config["gopro"]
        self.push_config = self.config["pushbullet"]
        self.photo_timer = self.config["photo_timer"]["minutes"]
        self.keep_alive_timer = self.config["keep_alive"]["minutes"]
        self.debug_level = None

        self.is_send_20_min_alert = False
        self.last_offline_alert_time = None
        self.last_photo_minute = None
        self.execution_start_time = datetime.datetime.now()

        self.wifi_retry_counter = 0
        self.reach_for_help_counter = 0
        self.photo_capture_error_counter = 0
        self.error_retries_counter = 0

        self.restart_counter = -1 # because it will be incremented before the first photo
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
        self.restart_counter += 1
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
        minute = now.minute
        second = now.second

        if minute in self.photo_timer and second < 30:
            if self.last_photo_minute != minute:
                logger.info("It's time to take a photo. Transitioning to TAKE_PHOTO.")
                self.state = "TAKE_PHOTO"
            else:
                logger.debug("Already took a photo this minute. Doing nothing.")
        # Only 20 sec. here, because it usually takes 25 seconds to complete, and there's no need to do it twice
        elif minute in self.keep_alive_timer and second < 20:
            self.keep_alive(True)
        else:
            self.keep_alive(False)

    def handle_take_photo_state(self):
        gopro_ssid = self.gopro_config["ssid"]
        if not self.ensure_wifi_connected(gopro_ssid):
            # If we can’t connect to GoPro Wi-Fi, error out
            logger.error(f"Failed to connect to GoPro Wi-Fi. We are in [{self.state}].")
            # self.state = "ERROR"
            return

        try:
            self.take_photo()
            self.last_photo_minute = datetime.datetime.now().minute

            self.state = "SEND_UPDATE"
        except Exception as e:
            logger.error(f"Error taking photo: {e}. Check logs for more info.")
            self.photo_capture_error_counter += 1
            self.state = "ERROR"

    def handle_send_update_state(self):
        """
        Switch to router Wi-Fi, time sync, send status, save state,
        then switch back to GoPro Wi-Fi to keep it alive. Return to WAITING when done.
        """
        router_ssid = self.wifi_config["ssid"]

        if not self.ensure_wifi_connected(router_ssid):
            logger.error(f"Failed to connect to {router_ssid}. ERROR.")
            self.state = "ERROR"
            return

        self.sync_time()
        self.send_status()
        self.save_state()

        gopro_ssid = self.gopro_config["ssid"]
        if not self.ensure_wifi_connected(gopro_ssid):
            logger.error(f"Failed to reconnect to {gopro_ssid} after sending status. ERROR.")
            self.state = "ERROR"
            return

        logger.info("Update complete. Returning to WAITING.")
        self.state = "WAITING"

    def handle_error_state(self):
        """
          If that fails too many times, we reboot the r-pi.
        """
        self.error_retries_counter += 1
        logger.error(f"Error State reached. Retry attempt {self.error_retries_counter} / {self.max_error_retries}.")

        if self.error_retries_counter < self.max_error_retries:
            logger.info("Will attempt to recover by returning to WAITING.")
            self.state = "WAITING"
        elif self.photo_capture_error_counter > 3:
            logger.error("Too many photo capture errors. Will attempt to recover by returning to WAITING.")
            self.state = "OFFLINE_ALERT"
        else:
            logger.error("Exceeded max error retries. Considering a forced reboot or state reset.")
            # subprocess.run(["sudo", "reboot"]) TODO do this if from the first error didn't pass more than 4..5 minutes
            # if more than 5 minutes passed.. there is a good chance GoPro is off, so we can't recover.
            self.state = "WAITING"
            self.error_retries_counter = 0

    def handle_offline_alert_state(self):
        """
        Repeatedly tries to connect to router Wi-Fi,
        then attempts GoPro Wi-Fi. If both fail, remains offline.

        - Send one immediate 'GoPro offline' notification if this is the first time.
        - Then send repeated notifications every 20 minutes if it remains offline (and there's internet).
        """
        router_ssid = self.wifi_config["ssid"]
        now = datetime.datetime.now()

        if not hasattr(self, "last_offline_alert_time"):
            self.last_offline_alert_time = now - datetime.timedelta(hours=1)

        # Attempt to connect to router
        if self.ensure_wifi_connected(router_ssid):
            self.last_offline_alert_time = now

            gopro_ssid = self.gopro_config["ssid"]
            if self.ensure_wifi_connected(gopro_ssid):
                logger.info("Router AND GoPro reconnected. Returning to WAITING.")
                self.state = "WAITING"
            else:
                time_since_last_offline_alert = now - self.last_offline_alert_time
                if time_since_last_offline_alert.total_seconds() >= 1200:  # 20 minutes
                    self.send_notification(
                        "GoPro OFFLINE!",
                        "\nSTILL CAN NOT connect to GoPro. [20 min repeat] Sent at "
                    )
                    self.last_offline_alert_time = now
                else:
                    if not self.is_send_20_min_alert:
                        # Send an immediate, one-time alert
                        self.send_notification(
                            "GoPro OFFLINE!",
                            "\nFirst-time alert: I CAN NOT connect to GoPro. Sent at "
                        )
                        # The assumption is we can't recover from this, so we set this flag True.
                        # It will keep sending the 20-min alert until user intervention.
                        self.is_send_20_min_alert = True
                        self.last_offline_alert_time = now
        else:
            # Router is offline too, or we can't connect.
            self.restart_wifi()
            # if no change, a rpi reboot would be an idea as well. But may not fix anything if gopro wifi is down.
            logger.warning("Router is offline as well; can't send notification. Remain in OFFLINE_ALERT.")

    # ------------------------------------------------------------------

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
            logger.error(f"Failed to get current wifi: x")
            return None

    def switch_wifi(self, target_ssid):
        pwd = self._determine_wifi_password(target_ssid)
        max_tries = 5
        for attempt in range(max_tries):
            logger.info(f"Trying to connect to {target_ssid}, attempt {attempt + 1}/{max_tries}")
            try:
                cmd = f"nmcli dev wifi connect '{target_ssid}' password '{pwd}'"
                subprocess.run(cmd, shell=True, check=True)
                time.sleep(5)  # wait for wifi to settle
                if (self.get_current_wifi() or "").lower() == target_ssid.lower():
                    logger.info(f"Connected to {target_ssid} successfully.")
                    return True
            except subprocess.CalledProcessError as e:
                logger.warning(f"nmcli connect attempt failed. SSID not found or password is incorrect. Message x")
                time.sleep(3)

        logger.error(f"Failed to connect to {target_ssid} after {max_tries} tries.")
        return False

    def _determine_wifi_password(self, ssid):
        if ssid == self.gopro_config["ssid"]:
            return self.gopro_config["pwd"]
        else:
            return self.wifi_config["pwd"]

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

    def keep_alive(self, send_wol):
        logger.info("Attempting to keep GoPro Wi-Fi alive..")

        gopro_ssid = self.gopro_config["ssid"]
        if not self.ensure_wifi_connected(gopro_ssid):
            logger.warning("Cannot keep alive because we can't connect to GoPro Wi-Fi.")
            return  # We’re probably in OFFLINE_ALERT or ERROR now

        # Send WOL every 9 minutes
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

    def take_photo(self):
        try:
            logger.info("Waking up the GoPro with Magic package.")
            self.send_wol()
            time.sleep(2)

            # Connect to camera
            self.check_network_reachable(self.gopro_config["ip"])
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

    def send_status(self):
        # logger.error(f"[STATUS] {title}: {message}")
        url = "https://api.pushbullet.com/v2/pushes"
        headers = {
            "Access-Token": self.push_config["api_key"],
            "Content-Type": "application/json"
        }
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        data = {
            "type": "note",
            "title": "Time-lapse update",
            "body": f"Don't worry.. all iz good! \n{timestamp} "
                    f"- Temp is [{self.rpi_temp()}] "
                    f"- Restart counter: [{self.restart_counter}]"
        }
        try:
            resp = requests.post(url, headers=headers, json=data)
            if resp.status_code == 200:
                logger.info(f"Push notification sent successfully --> [STATUS] {timestamp} -- {data}")
            else:
                logger.error(f"This is PushBullet's error: {resp.status_code}, {resp.text}")
        except Exception as e:
            logger.error(f"Error sending status: {e}")

    def send_notification(self, title, message):
        logger.error(f"[ALERT] {title}: {message}")
        url = "https://api.pushbullet.com/v2/pushes"
        headers = {
            "Access-Token": self.push_config["api_key"],
            "Content-Type": "application/json"
        }
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        data = {
            "type": "note",
            "title": f"[ALERT] {title}",
            "body": f"{message} -- [{timestamp}]"
        }
        try:
            resp = requests.post(url, headers=headers, json=data)
            if resp.status_code == 200:
                logger.info("Push notification sent..")
            else:
                logger.error(f"Pushbullet error: {resp.status_code} -> {resp.text}")
        except Exception as e:
            logger.error(f"Error sending pushbullet: {e}")

    def sync_time(self):
        try:
            logger.info("Syncing time via ntpdate..")
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
                logger.warning(f"Ping to {ip} failed. Attempt {attempt + 1}/{retries}.")
                self.restart_wifi()
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
            self.debug_level = new_config["debug_level"]
            self.push_config = new_config["pushbullet"]
            self.photo_timer = new_config["photo_timer"]["minutes"]
            self.keep_alive_timer = new_config["keep_alive"]["minutes"]

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
            "last_photo_minute": self.last_photo_minute if self.last_photo_minute else None,
            "last_offline_alert_time": self.fromisoformat_fallback(self.last_offline_alert_time.isoformat()) if self.last_offline_alert_time else None,
            "photo_capture_error_counter": self.photo_capture_error_counter if self.photo_capture_error_counter else 0,
            "reach_for_help_counter": self.reach_for_help_counter if self.reach_for_help_counter else 0,
            "error_retries": self.error_retries_counter if self.error_retries_counter else 0,
            "max_error_retries": self.max_error_retries if self.max_error_retries else 5,
            "execution_time_seconds": (datetime.datetime.now() - self.execution_start_time).total_seconds(),
            "restart_counter": self.restart_counter if self.restart_counter else 0,
        }
        try:
            with open(self.state_path, "w") as f:
                json.dump(data, f, indent=4)
            logger.info(f"Saved state to {self.state_path}.")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def fromisoformat_fallback(self, iso_string):  # Python 3.6 compatibility
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
        logger.info("Script is shutting down. Saving state..")

    def handle_sigint(self, signal_received, frame):
        logger.info("Ctrl+C received. Exiting gracefully..")
        sys.exit(0)


# ------------------------------------------------------------------

if __name__ == "__main__":
    controller = TimelapseController("config.json")
    controller.main_cycle()
