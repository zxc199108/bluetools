import dbus
import dbus.mainloop.glib
from gi.repository import GLib
import logging
import json
import threading
import signal
import sys
import os
import subprocess

from .logger import setup_logger
from .handlers import WiFiHandler, SystemHandler
from .ble_server import BLEServer
from .spp_server import SPPServer
from .agent import AutoPairAgent

logger = logging.getLogger(__name__)

# ==================== 硬编码默认配置 ====================
# 修改这里即可，无需 config.yaml

DEVICE_NAME = "Bluetools"              # 经典蓝牙设备名
BLE_DEVICE_NAME = "Bluetools-BLE"      # BLE 广播名
SPP_CHANNEL = 1                         # SPP 串口通道
AGENT_CAPABILITY = "DisplayOnly"        # 这个板子芯片只能用 DisplayOnly
PIN_CODE = "1234"                       # 手机输入 1234 配对

ALLOWED_COMMANDS = [
    "reboot", "shutdown", "poweroff", "ifconfig", "ip", "ping",
    "hostname", "uptime", "free", "df", "ps", "uname", "date",
    "whoami", "id", "lsblk", "dmesg", "journalctl",
]
# =====================================================


class BluetoolsServer:

    def __init__(self, server_ref=None):
        self._ref = server_ref or {}
        self._running = False
        self._loop = None
        self._bus = None
        self._adapter_path = "/org/bluez/hci0"
        self._agent = None

        self.wifi = WiFiHandler()
        self.system = SystemHandler(allowed_commands=ALLOWED_COMMANDS)

        self.ble = None
        self.spp = None

    @property
    def _capability(self):
        return self._ref.get("capability", AGENT_CAPABILITY)

    @property
    def _pin_code(self):
        return self._ref.get("pin", PIN_CODE)

    def start(self):
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        self._bus = dbus.SystemBus()
        self._loop = GLib.MainLoop()

        # 0) 控制器层面设好 IO 能力 + SSP
        self._set_controller_io_cap()

        # 1) 注册 agent
        self._register_agent()

        # 2) 初始化蓝牙适配器
        self._init_bluetooth_adapter()

        self.ble = BLEServer(
            self._bus,
            adapter_path=self._adapter_path,
            name=BLE_DEVICE_NAME,
        )
        self.ble.setup(
            on_wifi_ssid=self._on_ble_wifi_ssid,
            on_wifi_password=self._on_ble_wifi_password,
            on_wifi_connect=self._on_ble_wifi_connect,
            on_wifi_scan=self._on_ble_wifi_scan,
            on_system_cmd=self._on_ble_system_cmd,
        )
        self.ble.register()
        self.ble.start_advertising()

        self.spp = SPPServer(
            self._bus,
            adapter_path=self._adapter_path,
            channel=SPP_CHANNEL,
            name="Bluetools SPP",
            on_connect=self._on_spp_connect,
            on_disconnect=self._on_spp_disconnect,
            on_message=self._on_spp_message,
        )
        self.spp.register()

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        self._running = True
        logger.info("====================================")
        logger.info("  Bluetools server started")
        logger.info(f"  Device name : {DEVICE_NAME}")
        logger.info(f"  BLE name    : {BLE_DEVICE_NAME}")
        logger.info(f"  SPP channel : {SPP_CHANNEL}")
        logger.info(f"  Pair mode   : {self._capability}")
        logger.info(f"  Pairing PIN : {self._pin_code}")
        logger.info(f"  Web UI      : http://<board-ip>:5000")
        logger.info("====================================")

        try:
            self._loop.run()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        if not self._running:
            return
        self._running = False
        logger.info("Stopping Bluetools server...")
        if self._agent:
            self._agent.unregister()
        if self.ble:
            self.ble.unregister()
        if self.spp:
            self.spp.unregister()
        if self._loop:
            self._loop.quit()
        logger.info("Bluetools server stopped")

    def _set_controller_io_cap(self):
        """Use btmgmt to set IO capability at the controller/kernel level.
        This is the most reliable way to ensure NoInputNoOutput (Just Works)
        pairing on ARM64 boards where the BT chip driver may not fully
        support agent IO capability override.
        
        IO Caps: 0=DisplayOnly, 1=DisplayYesNo, 2=KeyboardOnly,
                 3=NoInputNoOutput, 4=KeyboardDisplay
        """
        io_cap_map = {
            "DisplayOnly": 0,
            "DisplayYesNo": 1,
            "KeyboardOnly": 2,
            "NoInputNoOutput": 3,
            "KeyboardDisplay": 4,
        }
        io_val = io_cap_map.get(self._capability, 3)
        
        cmds = [
            ["btmgmt", "ssp", "off"],
            ["btmgmt", "sc", "off"],
            ["btmgmt", "io-cap", str(io_val)],
            ["btmgmt", "pairable", "on"],
            ["btmgmt", "connectable", "on"],
            ["btmgmt", "discov", "on"],
            ["btmgmt", "name", DEVICE_NAME],
        ]
        
        for cmd in cmds:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if result.returncode != 0 and result.stderr:
                    logger.debug(f"btmgmt {' '.join(cmd[1:])}: {result.stderr.strip()}")
                else:
                    logger.info(f"btmgmt: {' '.join(cmd[1:])} OK")
            except FileNotFoundError:
                logger.warning("btmgmt not found, skip controller-level IO cap setting")
                return
            except Exception as e:
                logger.debug(f"btmgmt {' '.join(cmd[1:])}: {e}")

    def _init_bluetooth_adapter(self):
        """Set adapter: powered on, always discoverable, always pairable."""
        try:
            adapter = dbus.Interface(
                self._bus.get_object("org.bluez", self._adapter_path),
                "org.freedesktop.DBus.Properties",
            )
            adapter.Set("org.bluez.Adapter1", "Powered", True)
            adapter.Set("org.bluez.Adapter1", "Alias", DEVICE_NAME)
            adapter.Set("org.bluez.Adapter1", "DiscoverableTimeout", dbus.types.UInt32(0))
            adapter.Set("org.bluez.Adapter1", "Discoverable", True)
            adapter.Set("org.bluez.Adapter1", "PairableTimeout", dbus.types.UInt32(0))
            adapter.Set("org.bluez.Adapter1", "Pairable", True)
            logger.info(f"Bluetooth adapter ready: {DEVICE_NAME} (discoverable=always)")
        except dbus.exceptions.DBusException as e:
            logger.error(f"Failed to init Bluetooth adapter: {e}")
            raise

    def _register_agent(self):
        """Register auto-pair agent so headless pairing works without user input."""
        self._agent = AutoPairAgent(
            self._bus,
            path="/org/bluetools/agent",
            capability=self._capability,
            pin_code=self._pin_code,
            auto_accept=True,
        )
        self._agent.register()

    def _signal_handler(self, signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
        sys.exit(0)

    # --- BLE callbacks ---

    def _on_ble_wifi_ssid(self, data):
        self._wifi_ssid = data.decode("utf-8", errors="replace")
        logger.info(f"BLE: wifi_ssid set = {self._wifi_ssid}")

    def _on_ble_wifi_password(self, data):
        self._wifi_password = data.decode("utf-8", errors="replace")
        logger.info("BLE: wifi_password set")

    def _on_ble_wifi_connect(self, data):
        ssid = getattr(self, "_wifi_ssid", "")
        password = getattr(self, "_wifi_password", "")
        if not ssid:
            self.ble.notify_wifi_status({"state": "error", "error": "no ssid"})
            return
        logger.info(f"BLE: wifi_connect -> {ssid}")
        threading.Thread(
            target=self._do_wifi_connect,
            args=(ssid, password, "ble"),
            daemon=True,
        ).start()

    def _on_ble_wifi_scan(self, data):
        logger.info("BLE: wifi_scan requested")
        threading.Thread(target=self._do_wifi_scan, args=("ble",), daemon=True).start()

    def _on_ble_system_cmd(self, data):
        try:
            msg = json.loads(data.decode("utf-8"))
        except json.JSONDecodeError:
            msg = {"command": data.decode("utf-8", errors="replace")}
        logger.info(f"BLE: system_cmd -> {msg}")
        threading.Thread(
            target=self._do_system_cmd, args=(msg, "ble"), daemon=True
        ).start()

    # --- SPP callbacks ---

    def _on_spp_connect(self, device):
        logger.info(f"SPP connected: {device}")

    def _on_spp_disconnect(self, device):
        logger.info(f"SPP disconnected: {device}")

    def _on_spp_message(self, device, msg):
        msg_type = msg.get("type", "")
        logger.info(f"SPP [{device[-8:]}]: {msg_type}")

        if msg_type == "wifi_scan":
            threading.Thread(
                target=self._do_wifi_scan, args=("spp", device), daemon=True
            ).start()
            return {"type": "wifi_scan_status", "status": "scanning"}

        elif msg_type == "wifi_connect":
            ssid = msg.get("ssid", "")
            password = msg.get("password", "")
            threading.Thread(
                target=self._do_wifi_connect, args=(ssid, password, "spp", device),
                daemon=True,
            ).start()
            return {"type": "wifi_connect_status", "status": "connecting", "ssid": ssid}

        elif msg_type == "wifi_disconnect":
            result = self.wifi.disconnect()
            return {"type": "wifi_disconnect_result", **result}

        elif msg_type == "wifi_status":
            result = self.wifi.status()
            return {"type": "wifi_status_result", **result}

        elif msg_type == "cmd":
            command = msg.get("command", "")
            args = msg.get("args", [])
            result = self.system.execute(command, args)
            msg_id = msg.get("id", 0)
            return {"type": "cmd_result", "id": msg_id, **result}

        elif msg_type == "dangerous_cmd":
            command = msg.get("command", "")
            result = self.system.execute_dangerous(command)
            msg_id = msg.get("id", 0)
            return {"type": "cmd_result", "id": msg_id, **result}

        else:
            return {"type": "error", "message": f"Unknown command: {msg_type}"}

    # --- Worker methods ---

    def _do_wifi_scan(self, source, device=None):
        result = self.wifi.scan()
        if source == "ble":
            self.ble.notify_wifi_scan(json.dumps(result))
        elif source == "spp" and device:
            self.spp.profile_obj.send(device, {"type": "wifi_scan_result", **result})
        logger.info(f"WiFi scan done ({source}): {len(result.get('networks', []))} networks")

    def _do_wifi_connect(self, ssid, password, source, device=None):
        self._notify_wifi_status({"state": "connecting", "ssid": ssid, "ip": ""})
        result = self.wifi.connect(ssid, password)
        if source == "ble":
            self.ble.notify_wifi_status(json.dumps(result))
        elif source == "spp" and device:
            self.spp.profile_obj.send(
                device, {"type": "wifi_connect_result", **result}
            )

    def _do_system_cmd(self, msg, source, device=None):
        command = msg.get("command", "")
        args = msg.get("args", [])
        dangerous = msg.get("dangerous", False)
        if dangerous or command in self.system._dangerous:
            result = self.system.execute_dangerous(command)
        else:
            result = self.system.execute(command, args)
        if source == "ble":
            self.ble.notify_system_result(json.dumps(result))
        elif source == "spp" and device:
            msg_id = msg.get("id", 0)
            self.spp.profile_obj.send(
                device, {"type": "cmd_result", "id": msg_id, **result}
            )
        logger.info(f"System cmd done ({source}): {command} -> {result.get('success')}")

    def _notify_wifi_status(self, status):
        if self.ble:
            self.ble.notify_wifi_status(json.dumps(status))
        if self.spp:
            try:
                self.spp.profile_obj.broadcast({"type": "wifi_status", **status})
            except Exception as e:
                logger.debug(f"SPP broadcast skipped: {e}")
