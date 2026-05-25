#!/usr/bin/env python3
"""
Android SPP client for Bluetools (Termux / Python).

Usage:
  python3 btclient.py pair                    # pair with board
  python3 btclient.py ping                    # test connection  
  python3 btclient.py wifi-scan               # scan WiFi
  python3 btclient.py wifi-connect SSID PASS  # connect WiFi
  python3 btclient.py cmd "uptime"            # run command
  python3 btclient.py shell                   # interactive shell
"""
import socket
import json
import sys
import os
import subprocess

BOARD_MAC = ""          # e.g. "AA:BB:CC:DD:EE:FF"
BOARD_NAME = "Bluetools"
PIN = "1234"
CHANNEL = 1


def get_mac():
    if BOARD_MAC:
        return BOARD_MAC
    print(f"Scanning for {BOARD_NAME}...")
    try:
        out = subprocess.check_output(
            ["hcitool", "scan"], text=True, timeout=15
        )
        for line in out.split("\n"):
            parts = line.strip().split("\t") if "\t" in line else line.strip().split(None, 1)
            if len(parts) >= 2 and BOARD_NAME in parts[1]:
                mac = parts[0]
                print(f"Found: {mac}")
                return mac
    except Exception as e:
        print(f"Scan failed: {e}")
    return None


def pair(mac):
    print(f"Pairing with {mac}...")
    script = f"agent on\ndefault-agent\npair {mac}\n{PIN}\nyes\nyes\nquit\n"
    subprocess.run(["bluetoothctl"], input=script, text=True, capture_output=True)
    print("Done.")


def connect(mac, channel=CHANNEL):
    sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    sock.settimeout(10)
    sock.connect((mac, channel))
    return sock


def send_recv(sock, msg, timeout=5):
    if isinstance(msg, dict):
        msg = json.dumps(msg, ensure_ascii=False) + "\n"
    if isinstance(msg, str):
        msg = msg.encode()
    if not msg.endswith(b"\n"):
        msg += b"\n"
    sock.sendall(msg)
    sock.settimeout(timeout)
    buf = b""
    try:
        while True:
            data = sock.recv(4096)
            if not data:
                break
            buf += data
            if b"\n" in buf:
                break
    except socket.timeout:
        pass
    for line in buf.decode("utf-8").strip().split("\n"):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return {"raw": line}
    return {"raw": ""}


def interactive(mac):
    sock = connect(mac)
    print(f"Connected to {mac}. Type JSON or 'quit'.\n")
    while True:
        try:
            line = input("> ")
        except (EOFError, KeyboardInterrupt):
            break
        if line.lower() in ("quit", "exit", "q"):
            break
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            msg = {"type": "cmd", "command": line, "args": []}
        resp = send_recv(sock, msg)
        print(json.dumps(resp, indent=2, ensure_ascii=False))
    sock.close()


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    mac = get_mac()

    if cmd == "pair":
        mac = get_mac() or BOARD_MAC or sys.argv[2] if len(sys.argv) > 2 else None
        if not mac:
            print("Usage: python3 btclient.py pair [MAC]")
            return
        pair(mac)

    elif cmd == "ping":
        s = connect(mac)
        r = send_recv(s, {"type": "ping"})
        print(json.dumps(r, indent=2))
        s.close()

    elif cmd == "wifi-scan":
        s = connect(mac)
        r = send_recv(s, {"type": "wifi_scan"})
        nets = r.get("networks", [])
        for n in nets:
            print(f"  {n.get('ssid','?'):20s} sig:{n.get('signal','?')}  {n.get('security','')}")
        s.close()

    elif cmd == "wifi-connect":
        ssid = sys.argv[2] if len(sys.argv) > 2 else ""
        pw = sys.argv[3] if len(sys.argv) > 3 else ""
        if not ssid:
            print("Usage: python3 btclient.py wifi-connect SSID [PASSWORD]")
            return
        s = connect(mac)
        r = send_recv(s, {"type": "wifi_connect", "ssid": ssid, "password": pw})
        print(json.dumps(r, indent=2))
        s.close()

    elif cmd == "cmd":
        c = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "uptime"
        s = connect(mac)
        r = send_recv(s, {"type": "cmd", "command": c, "args": []})
        print(r.get("output", r.get("error", "")))
        s.close()

    elif cmd == "shell":
        interactive(mac)

    else:
        print("Usage: python3 btclient.py {pair|ping|wifi-scan|wifi-connect|cmd|shell}")
        print(f"  Set BOARD_MAC={BOARD_MAC or 'your-board-mac'} in script for faster connections")


if __name__ == "__main__":
    main()
