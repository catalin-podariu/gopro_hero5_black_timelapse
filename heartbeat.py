#!/usr/bin/env python3

import os
import subprocess
import sys
from pathlib import Path
import json
import time

import board
import busio
from PIL import Image, ImageDraw, ImageFont
import adafruit_ssd1306

# --------------------------------------------------------
# CONFIGURATION
# sudo pip3 install adafruit-blinka adafruit-circuitpython-ssd1306
# chmod +x /home/pi/heartbeat.py

# Also enable I2C on the Pi via sudo raspi-config, then verify your display appears at 0x3C or 0x3D with i2cdetect -y 1.
# To do that, go to Interfacing Options -> I2C -> Enable I2C
# --------------------------------------------------------
with open("config.json", "r") as f:
    config = json.load(f)

AWK_SCRIPT_PATH = config["heartbeat"]["awk_script"]
LOGS_DIR = config["logging_path"]
STATE_FILE = config["heartbeat"]["state_file"]

# Display sizing:
DISPLAY_WIDTH = 128
DISPLAY_HEIGHT = 64

# We want to store 60 chars: 4 rows x 15 columns
ROWS = 4
COLS = 15  # total 60

# Try a bigger font; fallback to default if not available
try:
    # Adjust size if you want even bigger text
    FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 11)
except:
    FONT = ImageFont.load_default()

# --------------------------------------------------------
# SETUP I2C + OLED
# --------------------------------------------------------
i2c = busio.I2C(board.SCL, board.SDA)
oled = adafruit_ssd1306.SSD1306_I2C(DISPLAY_WIDTH, DISPLAY_HEIGHT, i2c, addr=0x3C)

# Clear display at startup
oled.fill(0)
oled.show()


# --------------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------------
def draw_screen_offline():
    """
    Draw a big OFFLINE screen (clear everything else).
    """
    image = Image.new("1", (DISPLAY_WIDTH, DISPLAY_HEIGHT))
    draw = ImageDraw.Draw(image)

    draw.text((0, 0),  "GOPRO TIMELAPSE", font=FONT, fill=255)
    draw.text((0, 16), "###############", font=FONT, fill=255)
    draw.text((0, 28), "   OFFLINE",     font=FONT, fill=255)
    draw.text((0, 40), "###############", font=FONT, fill=255)

    oled.image(image)
    oled.show()


def draw_screen_normal(ring_buffer):
    """
    ring_buffer: list of 60 single-character events.
                 ring_buffer[0] is newest, ring_buffer[-1] is oldest.
    We'll display them in 4 rows x 15 columns, newest at top-left.
    """
    image = Image.new("1", (DISPLAY_WIDTH, DISPLAY_HEIGHT))
    draw = ImageDraw.Draw(image)

    # Header lines
    draw.text((0, 0),  "GOPRO TIMELAPSE", font=FONT, fill=255)

    # We'll place the ring-buffer text starting at row y=28 or so
    start_y = 14
    line_spacing = 10  # vertical spacing for each line

    for row_index in range(ROWS):
        start = row_index * COLS
        end = start + COLS
        row_events = ring_buffer[start:end]
        row_str = "".join(row_events)
        # Optionally prefix row number. E.g., "1--@---"
        line_text = f"{row_index+1} {row_str}"

        y = start_y + row_index * line_spacing
        draw.text((0, y), line_text, font=FONT, fill=255)

    oled.image(image)
    oled.show()


def draw_screen_first_run():
    """
    A special splash screen when there's no prior state.
    """
    image = Image.new("1", (DISPLAY_WIDTH, DISPLAY_HEIGHT))
    draw = ImageDraw.Draw(image)

    draw.text((0, 0),  "GOPRO TIMELAPSE",   font=FONT, fill=255)
    draw.text((0, 14), "###############",   font=FONT, fill=255)
    draw.text((0, 28), "-by mrbigheart-",    font=FONT, fill=255)
    draw.text((0, 42), "-------2025---",    font=FONT, fill=255)
    draw.text((0, 56), "###############",   font=FONT, fill=255)

    oled.image(image)
    oled.show()


def load_ring_buffer():
    """
    Loads a ring buffer of 60 chars from STATE_FILE.
    If it doesn’t exist or is malformed, returns an empty list.
    """
    if not os.path.isfile(STATE_FILE):
        return []
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        data = f.read().strip()
        # We expect exactly 60 single-char events
        if len(data) == 60:
            return list(data)  # newest at index 0
        return []


def save_ring_buffer(ring_buffer):
    """
    Saves the ring buffer to STATE_FILE as a 60-character string.
    ring_buffer[0] is newest; ring_buffer[59] is oldest.
    """
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write("".join(ring_buffer))


def get_latest_log():
    """
    Return the path to the newest .log in LOGS_DIR, or None if none found.
    """
    log_files = sorted(
        Path(LOGS_DIR).glob("*.log"),
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )
    return str(log_files[0]) if log_files else None


def get_event_char(log_path):
    """
    Run the AWK script on the newest log, capture single-char result:
      '?' | '|' | '@' | '+' | '-'
    Return '-' if something goes wrong or no logs.
    """
    if not log_path:
        return "-"
    try:
        # If your log is big, consider tailing a bigger slice to capture more events
        cmd = f"tail -n 300 '{log_path}' | '{AWK_SCRIPT_PATH}'"
        output = subprocess.check_output(cmd, shell=True, text=True).strip()

        if len(output) == 1:
            return output
        return "-"
    except Exception as e:
        print(f"Error running AWK script: {e}", file=sys.stderr)
        return "-"


def main():
    # Load ring buffer
    ring_buffer = load_ring_buffer()

    if len(ring_buffer) != 60:
        # If no valid prior state, show "first run" splash just once
        draw_screen_first_run()
        time.sleep(5) # Show for 5 seconds

        # Initialize fresh ring buffer
        ring_buffer = ["-"] * 60

    # Find the newest log
    log_path = get_latest_log()

    # Figure out this minute’s event
    event_char = get_event_char(log_path)

    # Shift ring buffer: remove oldest, insert new at the front
    ring_buffer.pop()
    ring_buffer.insert(0, event_char)

    # If OFFLINE => draw offline screen, else normal
    if event_char == "?":
        draw_screen_offline()
    else:
        draw_screen_normal(ring_buffer)

    # Save ring buffer for next run
    save_ring_buffer(ring_buffer)


if __name__ == "__main__":
    main()
