import atexit
import datetime
import signal
import sys
import time

from gptl_util import sync_time
from gptl_gopro import GptlGopro
from gptl_notification import GptlNotification
from gptl_wifi import GptlWifi
from gptl_config import GptlConfig
from gptl_state import GptlState
from gptl_logger import logger


class TimelapseController:
    def __init__(self):
        self.config = GptlConfig().get_config()

        # this is the default value. also.. 'state' is NOT saved in state.json
        self.state = "WAITING"
        self.state_path = "state.json"

        self.wifi_config = self.config["router"]
        self.gopro_config = self.config["gopro"]
        self.push_config = self.config["pushbullet"]
        self.photo_timer = self.config["photo_timer"]["minutes"]
        self.keep_alive_timer = self.config["keep_alive"]["minutes"]

        self.restart_counter = -1 # because it will be incremented before the first photo
        self.max_error_retries = 5

        self.gptl_gopro = GptlGopro(self.gopro_config)
        self.gptl_wifi = GptlWifi(self.wifi_config, self.gopro_config)
        self.gptl_state = GptlState(self.state_path)
        self.gptl_notification = GptlNotification(self.push_config, self.restart_counter)

        self.is_send_20_min_alert = False
        self.last_offline_alert_time = None
        self.last_photo_minute = None
        self.execution_start_time = datetime.datetime.now()

        self.photo_capture_error_counter = 0
        self.error_retries_counter = 0

        signal.signal(signal.SIGINT, self.handle_sigint)
        atexit.register(self.on_exit)

    # ------------------------------------------------------------------
    #                           MAIN CYCLE
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
                logger.info(f"Starting main cycle. Current state [{self.state}]")
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
    #                           MAIN CYCLE
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
            self.gptl_wifi.keep_alive(True)
        else:
            self.gptl_wifi.keep_alive(False)

    def handle_take_photo_state(self):
        gopro_ssid = self.gopro_config["ssid"]
        if not self.gptl_wifi.ensure_wifi_connected(gopro_ssid):
            # If we can’t connect to GoPro Wi-Fi, error out
            logger.error(f"Failed to connect to GoPro Wi-Fi. We are in [{self.state}].")
            # self.state = "ERROR"
            return

        try:
            self.gptl_gopro.take_photo()
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

        if not self.gptl_wifi.ensure_wifi_connected(router_ssid):
            logger.error(f"Failed to connect to {router_ssid}. ERROR.")
            self.state = "ERROR"
            return

        sync_time()
        self.gptl_notification.send_status()
        self.gptl_state.save_state()

        gopro_ssid = self.gopro_config["ssid"]
        if not self.gptl_wifi.ensure_wifi_connected(gopro_ssid):
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
        if self.gptl_wifi.ensure_wifi_connected(router_ssid):
            self.last_offline_alert_time = now

            gopro_ssid = self.gopro_config["ssid"]
            if self.gptl_wifi.ensure_wifi_connected(gopro_ssid):
                logger.info("Router AND GoPro reconnected. Returning to WAITING.")
                self.state = "WAITING"
            else:
                time_since_last_offline_alert = now - self.last_offline_alert_time
                if time_since_last_offline_alert.total_seconds() >= 1200:  # 20 minutes
                    self.gptl_notification.send_alert(
                        "GoPro OFFLINE!",
                        "\nSTILL CAN NOT connect to GoPro. [20 min repeat] Sent at "
                    )
                    self.last_offline_alert_time = now
                else:
                    if not self.is_send_20_min_alert:
                        # Send an immediate, one-time alert
                        self.gptl_notification.send_alert(
                            "GoPro OFFLINE!",
                            "\nFirst-time alert: I CAN NOT connect to GoPro. Sent at "
                        )
                        # The assumption is we can't recover from this, so we set this flag True.
                        # It will keep sending the 20-min alert until user intervention.
                        self.is_send_20_min_alert = True
                        self.last_offline_alert_time = now
        else:
            self.gptl_wifi.restart_wifi()
            logger.warning("Router is offline as well; can't send notification. Remain in OFFLINE_ALERT.")


    def on_exit(self):
        self.gptl_state.save_state()
        logger.info(f"Script ran for {(datetime.datetime.now() - self.execution_start_time).total_seconds()} seconds.")
        logger.info("Script is shutting down. Saving state..")

    def handle_sigint(self, signum, frame):
        logger.info("Ctrl+C received. Exiting gracefully..")
        sys.exit(0)

# ------------------------------------------------------------------

if __name__ == "__main__":
    controller = TimelapseController()
    controller.main_cycle()
