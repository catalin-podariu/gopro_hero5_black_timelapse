#!/bin/bash

# Makes sure the timelapse service is running and the log file being written to.
# If the log file is stale we assume the script got stuck, so the service is restarted asap!

# to edit crontab: sudo crontab -e and to check crontab: sudo crontab -l
# add this line * * * * * /home/timelapse/monitor_heartbeat.sh >> /home/timelapse/logs/monitor_heartbeat_log.txt 2>&1
# sudo systemctl daemon-reload
# sudo systemctl enable crontab.service
# sudo systemctl start crontab.service

LOG_DIR="/home/timelapse/logs"
TIMELAPSE_SERVICE="timelapse.service"
MAX_INTERVAL=40 # even this is a lot..

# Find the most recent log file matching the pattern
LOG_FILE=$(find "$LOG_DIR" -type f -name "daily_logs_*" -printf '%T@ %p\n' | sort -n | awk 'END {print $2}')

if [[ -z "$LOG_FILE" ]]; then
    echo "$(date): No log file found in $LOG_DIR. Restarting $TIMELAPSE_SERVICE."
    sudo systemctl restart $TIMELAPSE_SERVICE
    exit 1
fi

LAST_MODIFIED=$(stat -c %Y "$LOG_FILE")
CURRENT_TIME=$(date +%s)
AGE=$((CURRENT_TIME - LAST_MODIFIED))

if [[ $AGE -gt $MAX_INTERVAL ]]; then
    echo "$(date): Log file is stale (age: $AGE seconds, file: $LOG_FILE). Restarting $TIMELAPSE_SERVICE."
    sudo systemctl restart $TIMELAPSE_SERVICE
    exit 1
fi

UPTIME=$(sudo uptime -p)

echo "$(date): Still kickin' (age: $AGE seconds for $LOG_FILE). Uptime: $UPTIME"
