
import datetime
import subprocess
from lib.logger import logger

# This class is a collection of utility functions that are used in multiple places

def sync_time():
    try:
        logger.info("Syncing time via ntpdate..")
        subprocess.run(["sudo", "ntpdate", "-u", "pool.ntp.org"], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info("Time sync successful.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Time sync failed: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in time sync: {e}")

def rpi_temp():
    try:
        temp = subprocess.run(["vcgencmd", "measure_temp"], capture_output=True, text=True)
        if temp.returncode == 0:
            temp_value = float(temp.stdout.strip().split('=')[1].replace("'C", ""))
            return f"NORMAL - {temp_value}" if temp_value < 60.0 else f"HIGH - {temp_value}"
        else:
            return "UNKNOWN"
    except subprocess.CalledProcessError as e:
        logger.error(f"Error getting temperature: {e}")
    except Exception as e:
        logger.error(f"Unexpected error getting temperature: {e}")

def from_iso_format_fallback(iso_string):  # Python 3.6 compatibility
    try:
        return datetime.datetime.strptime(iso_string, "%Y-%m-%dT%H:%M:%S.%f")
    except ValueError:
        return datetime.datetime.strptime(iso_string, "%Y-%m-%dT%H:%M:%S")
