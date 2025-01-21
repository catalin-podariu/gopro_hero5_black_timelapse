import os
import json
import logging
import logging.handlers
from datetime import datetime

with open("config.json", "r") as config_file:
    config = json.load(config_file)

LOG_DIR = config["logging_path"]

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

logger = logging.getLogger("CentralLogger")
logger.setLevel(logging.DEBUG)

log_filename = os.path.join(LOG_DIR, f"daily_logs_{datetime.now().strftime('%Y_%m_%d')}.log")
file_handler = logging.handlers.TimedRotatingFileHandler(
    log_filename,
    when="midnight",  # Rotate at midnight
    interval=1,       # Rotate every 1 day
    backupCount=0,    # Keep all logs
)

# TimedRotatingFileHandler
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# ConsoleHandler prints to stdout
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
