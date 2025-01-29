
# This uses the PushBullet API to send notifications to the user's phone.

import json
import requests
import datetime
import gptl_util

from gptl_logger import logger


class GptlNotification:
    def __init__(self, push_config, restart_counter):
        self.push_config = push_config
        self.restart_counter = restart_counter


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
                    f"- Temp is [{gptl_util.rpi_temp()}] "
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

    def send_alert(self, title, message):
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
                logger.info("Alert notification sent..")
            else:
                logger.error(f"Pushbullet error: {resp.status_code} -> {resp.text}")
        except Exception as e:
            logger.error(f"Error sending alert notification: {e}")
