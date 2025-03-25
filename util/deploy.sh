#!/bin/bash

config_file='/Users/mrbigheart/workspace/personal/code/gopro_hero5_black_timelapse/config.json';
REMOTE_USER=$(jq -r .rpi.username $config_file);
REMOTE_HOST=$(jq -r .rpi.ip_lan $config_file);
REMOTE_DIR=$(jq -r .rpi.work_dir $config_file);

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Gimme some parameters first.. $0 <file_pattern> <download|deploy>"
    exit 1
fi

FILE_PATTERN=$1
DOWNLOAD_OR_DEPLOY=$2

if [ "$DOWNLOAD_OR_DEPLOY" == "download" ]; then
    echo "Downloading files matching pattern: $FILE_PATTERN from $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR"
    scp "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR" "$FILE_PATTERN"
    exit 0
elif [ "$DOWNLOAD_OR_DEPLOY" == "deploy" ]; then
    echo "Deploying files matching pattern: $FILE_PATTERN to $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR"
    scp "$FILE_PATTERN" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR"
    exit 0
fi

if [ $? -eq 0 ]; then
    echo "$DOWNLOAD_OR_DEPLOY successful!"
else
    echo "$DOWNLOAD_OR_DEPLOY failed."
fi
