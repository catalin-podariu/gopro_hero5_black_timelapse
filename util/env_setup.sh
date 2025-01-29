#!/usr/bin/env bash
#
# Prepares a fresh Raspberry Pi OS for the GoPro timelapse script + systemd service. (hopefully)
#

if [ "$(uname)" == "Darwin" ]; then
    echo "This script is for Linux (Raspbian) only. Please run it on a Raspberry Pi."
    exit 1
fi

set -e  # Exit on any error

TIMELAPSE_DIR="/home/timelapse"
GOPRO_ENV="/home/gopro_env"
SVC_USER="mrbigheart"

echo "==== Updating apt-get and upgrading existing packages ===="
sudo apt-get update
sudo apt-get upgrade -y

echo "==== Installing Python 3 and pip ===="
sudo apt-get install -y python3 python3-pip python3-venv

echo "==== Installing NetworkManager (for nmcli) ===="
sudo apt-get install -y network-manager

# Optional step: Switch from dhcpcd to NetworkManager if you want `nmcli` to manage Wi-Fi fully.
# This will disable dhcpcd service and enable network-manager.
# If you already use NetworkManager or prefer not to change the default, comment these lines.
echo "==== Disabling dhcpcd and enabling NetworkManager ===="
sudo systemctl stop dhcpcd || true
sudo systemctl disable dhcpcd || true
sudo systemctl enable NetworkManager
sudo systemctl start NetworkManager

echo "==== Installing ntpdate for time sync ===="
sudo apt-get install -y ntpdate

echo "==== Creating a Python virtual environment at $GOPRO_ENV ===="
sudo mkdir -p "$GOPRO_ENV"
sudo chown -R "$SVC_USER:$SVC_USER" "$GOPRO_ENV"
sudo -u "$SVC_USER" python3 -m venv "$GOPRO_ENV"

echo "==== Activating the venv and installing packages inside it ===="
sudo -u "$SVC_USER" bash -c "
    source $GOPRO_ENV/bin/activate
    pip install --upgrade pip
    pip install goprocam requests pushbullet.py
"

echo "==== Upgrading pip ===="
sudo pip3 install --upgrade pip --break-system-packages

echo "==== Installing Python libraries system-wide (optional) ===="
sudo pip3 install goprocam requests pushbullet.py jq --break-system-packages

echo "==== Ensuring $TIMELAPSE_DIR exists and is owned by $SVC_USER ===="
sudo mkdir -p "$TIMELAPSE_DIR"
sudo chown -R "$SVC_USER:$SVC_USER" "$TIMELAPSE_DIR"

echo "==== Creating systemd service files for timelapse and failure handling ===="

# timelapse.service
sudo tee /etc/systemd/system/timelapse.service >/dev/null <<EOF
[Unit]
Description=GoPro Timelapse Script
After=network-online.target
Wants=network-online.target

StartLimitIntervalSec=180
StartLimitBurst=3

[Service]
Type=simple

# Load configuration and execute script
ExecStart=/bin/bash -c "config_file='/home/timelapse/config/config.json'; username=$(jq -r .rpi_service.username $config_file); script_path=$(jq -r .rpi_service.path $config_file); work_dir=$(jq -r .rpi_service.work_dir $config_file); . /home/gopro_env/bin/activate && python $script_path"

Restart=on-failure
RestartSec=60

User=root
Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
WorkingDirectory=/home/timelapse

[Install]
WantedBy=multi-user.target
EOF

echo "==== Reloading systemd, enabling and starting timelapse services ===="
sudo systemctl daemon-reload
sudo systemctl enable timelapse.service

echo "==== Setup complete! ===="
echo "You can now reboot, and the timelapse script will run automatically."
echo "echoing.. sudo reboot"
