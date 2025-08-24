# This script will copy your project to /etc/myhargassner and install the systemd service
# Usage: sudo bash install_system_service.sh

set -e

SERVICE_NAME="myhargassner"
INSTALL_DIR="/etc/$SERVICE_NAME"
SERVICE_FILE="$SERVICE_NAME.service"

# Copy project files to /etc/myhargassner
mkdir -p "$INSTALL_DIR"
cp -r * "$INSTALL_DIR/"


# Install Python package system-wide (Debian/Ubuntu: allow with --break-system-packages)
cd "$INSTALL_DIR"
echo "Installing Python package system-wide. If you see an 'externally-managed-environment' error, using --break-system-packages."
if pip --version | grep -q 'python 3'; then
	pip install . --break-system-packages || {
		echo "pip install failed. Trying with pip3...";
		pip3 install . --break-system-packages;
	}
else
	pip3 install . --break-system-packages
fi

# Copy systemd service file
cp "$SERVICE_FILE" /etc/systemd/system/

# Reload systemd and enable service
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

# Start the service
systemctl start "$SERVICE_NAME"

echo "Service $SERVICE_NAME installed and started."
