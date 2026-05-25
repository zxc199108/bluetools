import subprocess
import json
import re
import logging
from threading import Lock

logger = logging.getLogger(__name__)


class WiFiHandler:
    """WiFi management using nmcli."""

    def __init__(self):
        self._lock = Lock()
        self._pending_scan = False

    def _run_nmcli(self, args, timeout=30):
        cmd = ["nmcli", "-t"] + args
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            logger.error(f"nmcli timed out: {' '.join(cmd)}")
            return -1, "", "timeout"
        except FileNotFoundError:
            logger.error("nmcli not found. Install network-manager.")
            return -1, "", "nmcli not found"

    def scan(self):
        with self._lock:
            logger.info("Starting WiFi scan...")
            code, out, err = self._run_nmcli(
                ["device", "wifi", "rescan"], timeout=10
            )
            import time

            time.sleep(3)
            code, out, err = self._run_nmcli(
                ["-f", "SSID,SIGNAL,SECURITY,BARS", "device", "wifi", "list"],
                timeout=15,
            )
            if code != 0:
                return {"success": False, "error": err or "scan failed"}

            networks = []
            for line in out.split("\n"):
                line = line.strip()
                if not line or line.startswith("SSID"):
                    continue
                parts = line.split(":")
                if len(parts) >= 3:
                    networks.append(
                        {
                            "ssid": parts[0],
                            "signal": parts[1] if len(parts) > 1 else "",
                            "security": parts[2] if len(parts) > 2 else "",
                        }
                    )
            logger.info(f"WiFi scan found {len(networks)} networks")
            return {"success": True, "networks": networks}

    def connect(self, ssid, password=""):
        with self._lock:
            logger.info(f"Connecting to WiFi: {ssid}")
            if password:
                code, out, err = self._run_nmcli(
                    [
                        "device",
                        "wifi",
                        "connect",
                        ssid,
                        "password",
                        password,
                    ],
                    timeout=60,
                )
            else:
                code, out, err = self._run_nmcli(
                    ["device", "wifi", "connect", ssid], timeout=60
                )

            if code == 0:
                logger.info(f"Connected to {ssid}")
                ip = self._get_ip()
                return {"success": True, "ssid": ssid, "ip": ip}
            else:
                logger.error(f"WiFi connection failed: {err}")
                return {"success": False, "error": err}

    def disconnect(self):
        with self._lock:
            iface = self._get_wifi_iface()
            if not iface:
                return {"success": False, "error": "no wifi interface found"}
            code, out, err = self._run_nmcli(
                ["device", "disconnect", iface], timeout=10
            )
            return {"success": code == 0, "error": err if code != 0 else ""}

    def status(self):
        iface = self._get_wifi_iface()
        if not iface:
            return {"state": "no_wifi", "ssid": "", "ip": ""}

        code, out, err = self._run_nmcli(
            ["-f", "GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS", "device", "show", iface],
            timeout=5,
        )
        if code != 0:
            return {"state": "unknown", "ssid": "", "ip": ""}

        status = {"state": "disconnected", "ssid": "", "ip": ""}
        for line in out.split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                key, val = line.split(":", 1)
                if key == "GENERAL.STATE":
                    status["state"] = val
                elif key == "GENERAL.CONNECTION":
                    status["ssid"] = val
                elif key == "IP4.ADDRESS":
                    m = re.match(r"(\d+\.\d+\.\d+\.\d+)", val)
                    if m:
                        status["ip"] = m.group(1)
            except ValueError:
                continue

        if "connected" in status.get("state", "").lower():
            short_state = "connected"
        elif "connecting" in status.get("state", "").lower():
            short_state = "connecting"
        elif "disconnected" in status.get("state", "").lower():
            short_state = "disconnected"
        else:
            short_state = status.get("state", "unknown")

        return {
            "state": short_state,
            "ssid": status["ssid"],
            "ip": status["ip"],
        }

    def _get_ip(self):
        iface = self._get_wifi_iface()
        if not iface:
            return ""
        code, out, err = self._run_nmcli(
            ["-f", "IP4.ADDRESS", "device", "show", iface], timeout=5
        )
        if code == 0:
            for line in out.split("\n"):
                if "IP4.ADDRESS" in line:
                    try:
                        _, val = line.split(":", 1)
                        m = re.match(r"(\d+\.\d+\.\d+\.\d+)", val.strip())
                        if m:
                            return m.group(1)
                    except ValueError:
                        pass
        return ""

    def _get_wifi_iface(self):
        code, out, err = self._run_nmcli(
            ["-t", "-f", "DEVICE,TYPE", "device", "status"], timeout=5
        )
        if code != 0:
            return ""
        for line in out.split("\n"):
            try:
                device, dtype = line.strip().split(":")
                if dtype == "wifi":
                    return device
            except ValueError:
                continue
        return ""


class SystemHandler:
    """System command execution."""

    def __init__(self, allowed_commands=None):
        self._allowed = set(allowed_commands or [])
        self._dangerous = {"reboot", "shutdown", "poweroff", "halt"}

    def execute(self, command, args=None):
        args = args or []
        if not self._is_allowed(command):
            return {"success": False, "output": f"Command not allowed: {command}"}

        full_cmd = [command] + list(args)
        logger.info(f"Executing: {' '.join(full_cmd)}")
        try:
            result = subprocess.run(
                full_cmd, capture_output=True, text=True, timeout=30
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout.strip() or result.stderr.strip(),
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "output": "Command timed out"}
        except FileNotFoundError:
            return {"success": False, "output": f"Command not found: {command}"}
        except Exception as e:
            return {"success": False, "output": str(e)}

    def execute_dangerous(self, command):
        """Execute dangerous commands like reboot with confirmation."""
        if command not in self._dangerous:
            return {"success": False, "output": f"Not a dangerous command: {command}"}
        logger.warning(f"Executing dangerous command: {command}")
        subprocess.Popen([command])
        return {"success": True, "output": f"{command} initiated"}

    def _is_allowed(self, command):
        return command in self._allowed or command in self._dangerous
