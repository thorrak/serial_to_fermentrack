#!/bin/bash
#
# Script to create a systemd service file for Serial-to-Fermentrack daemon
#

# Default values
INSTALL_DIR="/home/brewpi/serial-to-fermentrack"
USER="brewpi"
SERVICE_NAME="serial-to-fermentrack-daemon"
DAEMON_PATH="${INSTALL_DIR}/venv/bin/serial_to_fermentrack_daemon"

# Process command line arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-dir=*)
      INSTALL_DIR="${1#*=}"
      shift
      ;;
    --user=*)
      USER="${1#*=}"
      shift
      ;;
    --service-name=*)
      SERVICE_NAME="${1#*=}"
      shift
      ;;
    --daemon-path=*)
      DAEMON_PATH="${1#*=}"
      shift
      ;;
    --help)
      echo "Usage: $0 [options]"
      echo "Options:"
      echo "  --install-dir=DIR       Installation directory (default: /home/brewpi/serial-to-fermentrack)"
      echo "  --user=USER             User to run the service as (default: brewpi)"
      echo "  --service-name=NAME     Name of the systemd service (default: serial-to-fermentrack-daemon)"
      echo "  --daemon-path=PATH      Path to daemon executable (default: \${install-dir}/venv/bin/serial_to_fermentrack_daemon)"
      echo "  --help                  Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Use --help for usage information"
      exit 1
      ;;
  esac
done

# Generate service file content
SERVICE_CONTENT="[Unit]
Description=Serial-to-Fermentrack Multi-Device Daemon
After=network.target

[Service]
Type=simple
User=${USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${DAEMON_PATH}
Restart=on-failure
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target"

# Output the service file content
echo "Systemd service file content:"
echo "=============================="
echo "$SERVICE_CONTENT"
echo "=============================="
echo ""
echo "Installation instructions:"
echo "1. Save this content to /etc/systemd/system/${SERVICE_NAME}.service"
echo "2. Run: sudo systemctl daemon-reload"
echo "3. Run: sudo systemctl enable ${SERVICE_NAME}.service"
echo "4. Run: sudo systemctl start ${SERVICE_NAME}.service"

# Optionally install the service if running as root
if [[ $EUID -eq 0 ]]; then
  read -p "Do you want to install the service now? (y/n) " -n 1 -r
  echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Installing service to /etc/systemd/system/${SERVICE_NAME}.service"
    echo "$SERVICE_CONTENT" > "/etc/systemd/system/${SERVICE_NAME}.service"
    
    systemctl daemon-reload
    echo "Reloaded systemd configuration"
    
    systemctl enable "${SERVICE_NAME}.service"
    echo "Enabled ${SERVICE_NAME} service"
    
    echo "You can now start the service with:"
    echo "  sudo systemctl start ${SERVICE_NAME}.service"
  fi
fi