#!/bin/bash
# Bluetools installation script for Ubuntu ARM64
set -e

echo "=== Bluetools Installation ==="

# System dependencies (all from apt, no pip needed)
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

# Copy files
echo "[2/3] Installing bluetools to /opt..."
INSTALL_DIR="/opt/bluetools"
mkdir -p "$INSTALL_DIR"
cp -r "$(dirname "$0")/bluetools" "$INSTALL_DIR/"
cp "$(dirname "$0")/setup.py" "$INSTALL_DIR/"

# Systemd service
echo "[3/3] Installing systemd service..."
cp "$(dirname "$0")/bluetools.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable bluetools.service

# Persistent bluetooth settings
echo ""
echo "=== Setting persistent Bluetooth config ==="
btmgmt ssp off           # legacy PIN pairing
btmgmt sc off
btmgmt io-cap 0
btmgmt pairable on
btmgmt connectable on
btmgmt discov on
btmgmt name "Bluetools"

echo ""
echo "=== Installation complete ==="
echo ""
echo "Commands:"
echo "  Start:     systemctl start bluetools"
echo "  Status:    systemctl status bluetools"
echo "  Logs:      journalctl -u bluetools -f"
echo ""
echo "  Web UI:    http://<board-ip>:5000"
echo "  Device:    Bluetools"
echo "  BLE name:  Bluetools-BLE"
echo "  PIN:       1234"
