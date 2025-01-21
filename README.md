# GoPro Timelapse Controller

*Did you ever want to create an ultra-long GoPro timelapse without special equipment?*

*This project provides a Python-based solution to automate the entire workflow on a Raspberry Pi. 
It handles Wi-Fi switching between the Pi and the GoPro, schedules periodic photo captures, 
keeps the system time in sync, and even sends alerts if something goes wrong. All configurable.
Designed to run continuously as a `systemd` service, it ensures your timelapse runs 
smoothly for extended periods with minimal intervention.*

*This was designed for a six month timelapse, with two photos per hour. But feel free to adapt it.*


## Features

**1. State Machine**
- WAITING: Most of the time, the script idles on GoPro Wi-Fi, checking if it’s time to take a photo (photo_timer minutes).
- TAKE_PHOTO: Ensures we are on GoPro Wi-Fi, wakes the camera, captures a photo, then transitions to SEND_UPDATE.
- SEND_UPDATE: Switches to the home/router Wi-Fi, synchronizes time, sends a status notification, and saves script state. Returns to GoPro Wi-Fi when done.
- ERROR: If anything fails repeatedly, the script attempts to recover or eventually reboots / deletes state.
- OFFLINE_ALERT: If the script can’t connect to Wi-Fi or the GoPro for extended periods, it sends hourly push notifications (via PushBullet) until connectivity is restored.

**2. Keep-Alive Mechanism**
- Periodically sends a magic WOL packet and briefly toggles the GoPro into photo mode so it doesn’t go fully dormant.

**3. PushBullet Integration**
- On error or routine status updates, the script sends notes to a configured PushBullet account.

**4. Persistent State**
- Optionally saves counters (photo count, error retries, last photo time, etc.) to a JSON file, so the script can pick up where it left off after power outages.

**5. Logging**
- Uses a central Python logger, which can write to rotating files, console output, or both.


## Typical Flow

### **Waiting**

The script starts in `WAITING`, connected to the GoPro Wi-Fi. Every 5 seconds, it checks if the current minute is in `photo_timer`.
If it’s not time, it might call `keep_alive()` (optionally can send socket WOL packets) and keep the GoPro awake.

### **Taking Photos**
When the minute matches (e.g., `3` or `33`), the script transitions to `TAKE_PHOTO`. If the Pi isn’t on GoPro Wi-Fi, it switches automatically.
Wakes the camera, takes a photo, and logs the updated photo count.

### **Sending Updates**
Once a photo is taken, the script switches to your home Wi-Fi `SEND_UPDATE`, syncs the system time, and sends a status push to PushBullet.
It saves any counters (e.g., total photos) and then switches back to the GoPro Wi-Fi.

### **Error Handling**
If Wi-Fi switching or photo capture fails repeatedly, the script goes to `ERROR` (retries a few times), or goes into `OFFLINE_ALERT` if it can’t connect at all.
`OFFLINE_ALERT` sends push notifications every hour until connectivity is restored.
After max_error_retries, the script might remove its state file or even reboot the Pi.

### **Service Mode**
A systemd unit file `timelapse.service` runs this script at boot.
If the script fails 3 times in quick succession, `timelapse_failure.service` is called to send a “critical” PushBullet alert and optionally shut down the Pi.

#
#

Enjoy! :)

_And if you're gonna' whine about the monkey-patch or ASCII.. save it!<br>
I like it! =))_