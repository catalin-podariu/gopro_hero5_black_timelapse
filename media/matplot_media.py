#!/usr/bin/env python3

import sys
import re
from datetime import datetime, timedelta
import matplotlib.pyplot as plt


def parse_exif_log(filename):
    """
    Parses a log file containing lines like:
      File: ...; EXIF DateTimeOriginal: 2025:03:21 09:58:00;
    Returns a list of datetime objects (in ascending order).
    """
    import os

    # Regex to match something like:
    # "File: GOPR0001.JPG; EXIF DateTimeOriginal: 2025:03:21 09:58:00;"
    pattern = re.compile(r'^File:\s*.+?;\s*EXIF DateTimeOriginal:\s*([\d: ]+);')
    timestamps = []

    with open(filename, 'r', encoding='utf-8') as f:
        for line in f:
            match = pattern.search(line)
            if match:
                date_str = match.group(1).strip()  # e.g. "2025:03:21 09:58:00"
                try:
                    dt = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                    timestamps.append(dt)
                except ValueError:
                    pass

    timestamps.sort()
    return timestamps


def plot_day_vs_time(timestamps):
    """
    Given a list of datetime objects, plot:
      x-axis = day index (0-based from earliest date) but labeled as M/D
      y-axis = time of day in hours (0..24)
    """
    if not timestamps:
        print("No timestamps to plot!")
        return

    earliest_date = timestamps[0].date()

    day_indices = []
    hours_of_day = []

    for dt in timestamps:
        day_offset = (dt.date() - earliest_date).days
        hour_float = dt.hour + dt.minute / 60 + dt.second / 3600
        day_indices.append(day_offset)
        hours_of_day.append(hour_float)

    plt.figure("Day vs. Time of Day")

    # Scatter day_index on X, time-of-day on Y
    plt.scatter(day_indices, hours_of_day, marker='o')

    plt.title("GoPro time-lapse. Each dot represents one picture")
    plt.xlabel("Date (Month/Day)")
    plt.ylabel("Hour of Day (0–24)")
    plt.ylim([0, 24])  # time of day range
    plt.grid(True, which='major', axis='both', linestyle='--', alpha=0.2)

    # Build custom X ticks at each unique day offset
    unique_days = sorted(set(day_indices))
    # Create label string for each unique day offset
    day_labels = []
    for d in unique_days:
        # Convert offset back to a real date
        label_date = earliest_date + timedelta(days=d)
        # e.g. "Mar 21" or "03/21" or something
        day_labels.append(label_date.strftime("%m/%d"))

    plt.xticks(unique_days, day_labels, rotation=45)  # rotate if you want

    plt.show()


def main():
    if len(sys.argv) < 2:
        print("Usage: python day_time_plot.py /path/to/exif_log.txt")
        return

    exif_log_file = sys.argv[1]
    timestamps = parse_exif_log(exif_log_file)
    plot_day_vs_time(timestamps)


if __name__ == "__main__":
    main()
