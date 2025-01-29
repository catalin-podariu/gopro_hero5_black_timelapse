#!/bin/bash

# Makes sure the timelapse service is running and the log file being written to.
# If the log file is stale we assume the script got stuck, so the service is restarted asap!

LOGS_DIR="/home/timelapse/logs"
SERVICE_NAME="timelapse.service"
MAX_INTERVAL=40

# Find the most recent log file matching the pattern
LOG_FILE=$(find "$LOGS_DIR" -type f -name "daily_logs_*" -printf '%T@ %p\n' | sort -n | awk 'END {print $2}')

if [[ -z "$LOG_FILE" ]]; then
    echo "$(date): No log file found in $LOGS_DIR. Restarting $SERVICE_NAME."
    sudo systemctl restart $SERVICE_NAME
    exit 1
fi

LAST_MODIFIED=$(stat -c %Y "$LOG_FILE")
CURRENT_TIME=$(date +%s)
AGE=$((CURRENT_TIME - LAST_MODIFIED))

if [[ $AGE -gt $MAX_INTERVAL ]]; then
    echo "$(date): Log file is stale (age: $AGE seconds, file: $LOG_FILE). Restarting $SERVICE_NAME."
    sudo systemctl restart $SERVICE_NAME
    exit 1
fi

echo "$(date): Still kickin' age: $AGE seconds for $LOG_FILE)."
