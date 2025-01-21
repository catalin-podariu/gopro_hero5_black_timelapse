#!/usr/bin/env bash

#
# setup_timelapse.sh
# Prepares a fresh Raspberry Pi OS for the GoPro timelapse script + systemd services.
#
# Usage:
#   chmod +x setup_timelapse.sh
#   ./setup_timelapse.sh
#

if [ "$(uname)" == "Darwin" ]; then
    echo "This script is for Linux only. Please run it on a Raspberry Pi."
    exit 1
fi

set -e  # Exit on any error

echo "==== Updating apt-get and upgrading existing packages ===="
sudo apt-get update
sudo apt-get upgrade -y

echo "==== Installing Python 3 and pip ===="
sudo apt-get install -y python3 python3-pip python3-venv

echo "==== Installing NetworkManager (for nmcli) ===="
sudo apt-get install -y network-manager

# Optional step: Switch from dhcpcd to NetworkManager if you want `nmcli` to manage Wi-Fi fully.
# This will disable dhcpcd service and enable network-manager.
# If you're already using NetworkManager or prefer not to change the default, comment these lines.
echo "==== Disabling dhcpcd and enabling NetworkManager ===="
sudo systemctl stop dhcpcd
sudo systemctl disable dhcpcd
sudo systemctl enable NetworkManager
sudo systemctl start NetworkManager

echo "==== Installing ntpdate for time sync ===="
sudo apt-get install -y ntpdate

echo "==== Upgrading pip ===="
sudo pip3 install --upgrade pip

echo "==== Installing Python libraries ===="
# Includes whichever libs your timelapse script needs:
sudo pip3 install goprocam watchdog requests pushbullet.py jq

echo "==== Creating systemd service files for timelapse and failure handling ===="

# timelapse.service
cat <<'EOF' | sudo tee /etc/systemd/system/timelapse.service
[Unit]
Description=GoPro Timelapse Script
After=network-online.target
Wants=network-online.target

StartLimitIntervalSec=180
StartLimitBurst=3

[Service]
Type=simple
ExecStart=/bin/bash -c '
    config_file="/home/mrbigheart/workspace/gopro_timelapse/config.json";
    username=$(jq -r .rpi.username $config_file);
    script_path=$(jq -r .rpi.path $config_file);
    work_dir=$(jq -r .rpi.work_dir $config_file);
    source /home/mrbigheart/workspace/gopro_env/bin/activate && python $script_path
'
Restart=on-failure
RestartSec=60
WatchdogSec=120
User=pi
WorkingDirectory=/home/mrbigheart/workspace/gopro_timelapse
ExecStartPre=/bin/bash -c 'until ping -c1 8.8.8.8; do sleep 5; done'
OnFailure=timelapse_failure.service

[Install]
WantedBy=multi-user.target
EOF

# timelapse_failure.service
cat <<'EOF' | sudo tee /etc/systemd/system/timelapse_failure.service
[Unit]
Description=GoPro Timelapse Failure Handler
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/bin/bash -c '
    config_file="/home/mrbigheart/workspace/gopro_timelapse/config.json";
    api_key=$(jq -r .pushbullet.api_key $config_file);
    message="Time-lapse script cannot be started. Multiple failures. Assistance needed. Will shut-down now..";

    if ping -c 1 8.8.8.8 > /dev/null; then
        curl -X POST https://api.pushbullet.com/v2/pushes \
            -H "Access-Token: $api_key" \
            -H "Content-Type: application/json" \
            -d "{\"type\":\"note\",\"title\":\"Critical Alert\",\"body\":\"$(date +'%Y-%m-%d %H:%M:%S') -- $message\"}"
    fi

    # Shutdown the Raspberry Pi
    # sudo shutdown -h now
    echo "This would have shut down the rpi."
'

[Install]
WantedBy=multi-user.target
EOF

echo "==== Reloading systemd, enabling and starting timelapse services ===="
sudo systemctl daemon-reload
sudo systemctl enable timelapse.service
sudo systemctl enable timelapse_failure.service

echo "==== Setup complete! ===="
echo "You can now reboot, and the timelapse script will run automatically."
echo "  sudo reboot"


###############################################################################
# OPTIONAL: Auto-open a terminal with 'less' on the latest log file after boot.
# You can do this via .bashrc or systemd as well. Example:
#
# echo "sleep 10 && x-terminal-emulator -e 'less +F /home/mrbigheart/workspace/gopro_timelapse/logs/daily_logs_$(date +%Y_%m_%d).txt'" \
#     >> /home/pi/.bashrc
#
# That means after you log in, it waits 10s, then opens a terminal reading the log file.
###############################################################################

#  The script is quite straightforward. It installs the necessary packages, creates the systemd services, and sets up the failure handler.
#  The script also includes an optional step to switch from dhcpcd to NetworkManager. This is useful if you want to manage Wi-Fi connections using nmcli.
#  The script also includes a commented-out line to shut down the Raspberry Pi when the failure handler is triggered.
#  The script also includes an optional step to auto-open a terminal with the latest log file after boot.
#  You can run the script by executing the following commands:
#  chmod +x setup_timelapse.sh