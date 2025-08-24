#!/bin/bash
# Uninstall myghargassner system service and files
# Usage: sudo bash uninstall_system_service.sh

set -e

SERVICE_NAME="myshargassner"
INSTALL_DIR="/etc/$SERVICE_NAME"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"

# Stop and disable the systemd service
systemctl stop "$SERVICE_NAME" || true
systemctl disable "$SERVICE_NAME" || true

# Remove the systemd service file
if [ -f "$SERVICE_FILE" ]; then
    rm "$SERVICE_FILE"
fi

# Remove the installed files
if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
fi

# Uninstall the Python package
pip uninstall -y myshargassner || true

# Reload systemd
systemctl daemon-reload

# Optionally, remove logs or other files (uncomment if needed)
# rm -rf /var/log/myshargassner

echo "Service $SERVICE_NAME uninstalled."
