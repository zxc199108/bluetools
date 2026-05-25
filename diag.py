#!/usr/bin/env python3
"""Bluetooth diagnostics for Bluetools."""

import subprocess
import sys
import os


def run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return -1, "", str(e)


def check_missing_dbus(path, expected_iface):
    """Check if a D-Bus object path exists and has the expected interface."""
    try:
        import dbus
        bus = dbus.SystemBus()
        obj = bus.get_object("org.bluez", path)
        iface = dbus.Interface(obj, "org.freedesktop.DBus.Introspectable")
        xml = iface.Introspect()
        return expected_iface in xml
    except Exception:
        return False


def main():
    print("=" * 60)
    print("  Bluetools Bluetooth Diagnostics")
    print("=" * 60)

    # 1. Check BlueZ version
    print("\n[1] BlueZ version:")
    code, out, err = run(["bluetoothctl", "--version"])
    print(f"    {out or err}")

    # 2. Check hci0
    print("\n[2] Bluetooth adapter (hci0):")
    code, out, err = run(["hciconfig", "hci0"])
    if code == 0:
        for line in out.split("\n"):
            line = line.strip()
            if line:
                print(f"    {line}")
    else:
        code, out, err = run(["hciconfig", "-a"])
        if code == 0 and out:
            print(f"    {out}")
        else:
            print(f"    No adapter found! ({err})")

    # 3. Check adapter via bluetoothctl
    print("\n[3] Bluetooth adapter status:")
    code, out, err = run(["bluetoothctl", "show"])
    if code == 0:
        for line in out.split("\n"):
            line = line.strip()
            if line and "Controller" in line:
                print(f"    {line}")
            if line and ("Powered" in line or "Discoverable" in line or "Pairable" in line or "Alias" in line):
                print(f"    {line}")
    else:
        print(f"    Error: {err}")

    # 4. Check LE advertising support
    print("\n[4] BLE advertising supported:")
    code, out, err = run(["bluetoothctl", "show"])
    supported = "SupportedInstances" in out
    print(f"    {'YES' if supported else 'NO'} (check SupportedInstances)")
    if supported:
        for line in out.split("\n"):
            if "SupportedInstances" in line or "ActiveInstances" in line:
                print(f"    {line.strip()}")

    # 5. Check if D-Bus interfaces exist
    print("\n[5] D-Bus interfaces check:")
    try:
        import dbus
        bus = dbus.SystemBus()

        # Check adapter
        obj = bus.get_object("org.bluez", "/org/bluez/hci0")
        introspect = dbus.Interface(obj, "org.freedesktop.DBus.Introspectable")
        xml = introspect.Introspect()

        checks = {
            "GattManager1": "org.bluez.GattManager1" in xml,
            "LEAdvertisingManager1": "org.bluez.LEAdvertisingManager1" in xml,
            "ProfileManager1": "org.bluez.ProfileManager1" in xml,
        }
        for name, ok in checks.items():
            print(f"    {name}: {'OK' if ok else 'MISSING'}")
    except Exception as e:
        print(f"    D-Bus error: {e}")

    # 6. Check NetworkManager
    print("\n[6] NetworkManager (WiFi):")
    code, out, err = run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device", "status"])
    if code == 0:
        wifi_found = False
        for line in out.split("\n"):
            if "wifi" in line:
                wifi_found = True
                print(f"    {line}")
        if not wifi_found:
            print("    No WiFi device found in nmcli")
    else:
        print(f"    nmcli error: {err}")

    # 7. Python modules
    print("\n[7] Required Python modules:")
    modules = ["dbus", "gi", "yaml"]
    for m in modules:
        try:
            __import__(m)
            print(f"    {m}: OK")
        except ImportError:
            print(f"    {m}: MISSING - install with: apt install python3-{m}")

    # 8. Current BLE advertisements
    print("\n[8] Current BLE advertising status:")
    code, out, err = run(["btmgmt", "info"])
    if code == 0:
        for line in out.split("\n"):
            line = line.strip()
            if line and any(k in line for k in ["advertising", "name", "le", "advertise"]):
                print(f"    {line}")
    else:
        print(f"    btmgmt error: {err}")

    print("\n" + "=" * 60)
    print("  Run 'sudo systemctl start bluetools' to start the service")
    print("  Run 'journalctl -u bluetools -f' to watch logs")
    print("=" * 60)


if __name__ == "__main__":
    main()
