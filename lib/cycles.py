
import datetime

from lib.logger import logger
from lib.notification import Notification
from lib.util import sync_time
from lib.state import State
from lib.config import Config
from lib.wifi import Wifi
from lib.gopro import GoPro

class Cycles:

    def __init__(self):
        self.state = State()
        self.config = Config()
        self.wifi = Wifi()
        self.gopro = GoPro()
        self.notification = Notification()
        self.current_state = self.config.state

    def handle_waiting_state(self):
        now = datetime.datetime.now()
        minute = now.minute
        second = now.second

        if minute in self.config.photo_timer and second < 30:
            if self.config.last_photo_minute != minute:
                logger.info("It's time to take a photo. Transitioning to TAKE_PHOTO.")
                self.current_state = "TAKE_PHOTO"
            else:
                logger.debug("Already took a photo this minute. Doing nothing.")
        # Only 20 sec. here, because it usually takes 25 seconds to complete, and there's no need to do it twice
        elif minute in self.config.keep_alive_timer and second < 20:
            self.wifi.keep_alive(True)
        else:
            self.wifi.keep_alive(False)

    def handle_take_photo_state(self):
        now = datetime.datetime.now()
        minute = now.minute
        second = now.second

        gopro_ssid = self.config.gopro_config["ssid"]
        if not self.wifi.ensure_wifi_connected(gopro_ssid):
            # If we can’t connect to GoPro Wi-Fi, error out
            logger.error(f"Failed to connect to GoPro Wi-Fi. We are in [{self.current_state}].")
            return

        try:
            self.gopro.take_photo()
            self.config.last_photo_minute = datetime.datetime.now().minute
        except Exception as e:
            logger.error(f"Error taking photo: {e}. Check logs for more info.")
            self.config.photo_capture_error_counter += 1
            self.current_state = "ERROR"

        if (minute == 51 and second > 20) or (minute == 52 and second < 30):
            self.current_state = "SEND_UPDATE"
        else:
            self.current_state = "WAITING"

    def handle_send_update_state(self):
        """
        Switch to router Wi-Fi, time sync, send status, save state,
        then switch back to GoPro Wi-Fi to keep it alive. Return to WAITING when done.
        """
        router_ssid = self.config.router_config["ssid"]

        if not self.wifi.ensure_wifi_connected(router_ssid):
            logger.error(f"Failed to connect to {router_ssid}. ERROR.")
            self.current_state = "ERROR"
            return

        sync_time()
        self.notification.send_status()
        self.current_state.save_state()

        gopro_ssid = self.config.gopro_config["ssid"]
        if not self.wifi.ensure_wifi_connected(gopro_ssid):
            logger.error(f"Failed to reconnect to {gopro_ssid} after sending status. ERROR.")
            self.current_state = "ERROR"
            return

        logger.info("Update complete. Returning to WAITING.")
        self.current_state = "WAITING"

    def handle_error_state(self):
        """
          If that fails too many times, we reboot the r-pi.
        """
        self.config.error_retries_counter += 1
        logger.error(f"Error State reached. Retry attempt {self.config.error_retries_counter} / {self.config.max_error_retries}.")

        if self.config.error_retries_counter < self.config.max_error_retries:
            logger.info("Will attempt to recover by returning to WAITING.")
            self.current_state = "WAITING"
        elif self.config.photo_capture_error_counter > 3:
            logger.error \
                (f"Too many photo capture errors {self.config.photo_capture_error_counter}. Will attempt to recover by returning to WAITING.")
            self.current_state = "OFFLINE_ALERT"
        else:
            logger.error("Exceeded max error retries. Considering a forced reboot or state reset.")
            # if more than 5 minutes passed.. there is a good chance GoPro is off, so we can't recover.
            # todo: add a check to see if GoPro is reachable before rebooting
            self.current_state = "WAITING"
            self.config.error_retries_counter = 0

    def handle_offline_alert_state(self):
        """
        Repeatedly tries to connect to router Wi-Fi,
        then attempts GoPro Wi-Fi. If both fail, remains offline.

        - Send one immediate 'GoPro offline' notification if this is the first time.
        - Then send repeated notifications every 20 minutes if it remains offline (and there's internet).
        """
        router_ssid = self.config.router_config["ssid"]
        gopro_ssid = self.config.gopro_config["ssid"]
        now = datetime.datetime.now()

        # Make sure the attribute exists
        if not hasattr(self, "last_offline_alert_time"):
            # For a new session, pretend we started “offline” a while back
            # so we can send an alert quickly if needed
            self.config.last_offline_alert_time = now - datetime.timedelta(minutes=30)

        router_is_up = self.wifi.ensure_wifi_connected(router_ssid)
        gopro_is_up = False

        if router_is_up:
            gopro_is_up = self.wifi.ensure_wifi_connected(gopro_ssid)

        if router_is_up and gopro_is_up:
            # Fully online: reset everything
            logger.info("Router AND GoPro reconnected. Returning to WAITING.")
            self.current_state = "WAITING"
            self.config.last_offline_alert_time = None
            self.config.sending_alert_every_20_min = False
        else:
            # Either router is down, or GoPro is down (or both)
            if not self.config.last_offline_alert_time:
                self.config.last_offline_alert_time = now

            time_since_last_offline = now - self.config.last_offline_alert_time

            # If the router is offline, you might restart or do something else here...
            if not router_is_up:
                logger.warning("Router is offline, remain in OFFLINE_ALERT.")
                # self.restart_wifi()
                # Possibly bail out early, since we can’t reach the GoPro if router is off
                return

            # Otherwise, router is up but GoPro is offline
            if time_since_last_offline.total_seconds() >= 1200:  # 20-minute repeat
                self.notification.send_notification(
                    title="GoPro OFFLINE!",
                    message="STILL cannot connect to GoPro. [20 min repeat]. Sent at ..."
                )
                self.config.last_offline_alert_time = now
            else:
                # If we haven't started the repeating cycle, send that immediate “first offline” alert
                if not self.config.sending_alert_every_20_min:
                    self.notification.send_notification(
                        title="GoPro OFFLINE!",
                        message="I cannot connect to GoPro. Sending first-time alert at ..."
                    )
                    self.config.sending_alert_every_20_min = True
                    self.config.last_offline_alert_time = now
