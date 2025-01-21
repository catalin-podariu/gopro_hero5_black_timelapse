#!/bin/bash

REMOTE_USER="username"
REMOTE_HOST="hostname.local"
REMOTE_DIR="/home/timelapse"

if [ -z "$1" ]; then
    echo "Give me some parameters first.."
    exit 1
fi

FILE_PATTERN=$1

echo "Deploying files matching pattern: $FILE_PATTERN to $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR"
scp $FILE_PATTERN "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR"

if [ $? -eq 0 ]; then
    echo "Deployment successful!"
else
    echo "Deployment failed."
fi
