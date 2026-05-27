#!/bin/bash
# Bluetools installation script for Ubuntu ARM64
set -e

echo "=== Bluetools Installation ==="

# System dependencies
echo "[1/3] Installing system dependencies..."
apt-get update
apt-get install -y \
    python3 \
    python3-dbus \
    python3-gi \
    gir1.2-glib-2.0 \
    bluetooth \
    bluez \
    network-manager || true

# BlueZ configuration
echo "[2/4] Installing BlueZ config..."
cp "$(dirname "$0")/main.conf" /etc/bluetooth/main.conf
systemctl restart bluetooth

# Copy files
echo "[3/4] Installing bluetools to /opt..."
INSTALL_DIR="/opt/bluetools"
mkdir -p "$INSTALL_DIR"
cp -r "$(dirname "$0")/bluetools" "$INSTALL_DIR/"

# Systemd service
echo "[4/4] Installing systemd service..."
cp "$(dirname "$0")/bluetools.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable bluetools.service

echo ""
echo "=== Installation complete ==="
echo ""
echo "  Start:    systemctl start bluetools"
echo "  Status:   systemctl status bluetools"
echo "  Logs:     journalctl -u bluetools -f"
echo ""
echo "  Web UI:   http://<board-ip>:5000"
echo "  SPP:      channel 1"
echo "  PIN:      1234"
echo ""
echo "  Phone: pair with PIN 1234, then Serial Bluetooth Terminal"
