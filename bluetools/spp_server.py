import dbus
import dbus.service
import dbus.mainloop.glib
import logging
import json
import os
import socket
import threading
from gi.repository import GLib

logger = logging.getLogger(__name__)

BLUEZ_SERVICE = "org.bluez"
DBUS_PROP_IFACE = "org.freedesktop.DBus.Properties"
PROFILE_MANAGER_IFACE = "org.bluez.ProfileManager1"
PROFILE_IFACE = "org.bluez.Profile1"

SPP_UUID = "00001101-0000-1000-8000-00805f9b34fb"


class SerialProfile(dbus.service.Object):

    def __init__(self, bus, path, uuid, name, channel=1, on_connect=None,
                 on_disconnect=None, on_message=None):
        self.bus = bus
        self.path = path
        self.uuid = uuid
        self.name = name
        self.channel = channel
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect
        self._on_message = on_message
        self._connections = {}
        self._lock = threading.Lock()
        dbus.service.Object.__init__(self, bus, path)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != PROFILE_IFACE:
            raise dbus.exceptions.DBusException(
                f"Unknown interface: {interface}",
                name="org.freedesktop.DBus.Error.InvalidArgs",
            )
        return {
            "UUID": self.uuid,
            "Name": self.name,
            "Channel": dbus.types.UInt16(self.channel),
            "Role": "server",
            "RequireAuthentication": False,
        }

    @dbus.service.method(PROFILE_IFACE, in_signature="oha{sv}", out_signature="")
    def NewConnection(self, device, fd, properties):
        logger.info(f"SPP new connection: {device}")
        with self._lock:
            sock = socket.fromfd(fd, socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
            self._connections[device] = {
                "fd": fd,
                "sock": sock,
                "buf": b"",
            }
        if self._on_connect:
            self._on_connect(device)

        t = threading.Thread(
            target=self._read_loop, args=(device,), daemon=True, name=f"spp-{device[-8:]}"
        )
        t.start()

    def _read_loop(self, device):
        with self._lock:
            entry = self._connections.get(device)
        if not entry:
            return

        sock = entry["sock"]
        buf = b""
        try:
            while True:
                try:
                    data = sock.recv(1024)
                except (OSError, ConnectionError) as e:
                    logger.info(f"SPP connection closed: {device} ({e})")
                    break
                if not data:
                    logger.info(f"SPP connection ended: {device}")
                    break

                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if line:
                        try:
                            msg = json.loads(line.decode("utf-8"))
                            response = self._handle_message(device, msg)
                            if response:
                                self.send(device, response)
                        except json.JSONDecodeError as e:
                            logger.warning(f"SPP invalid JSON: {line[:100]} - {e}")
        except Exception as e:
            logger.error(f"SPP read error {device}: {e}")
        finally:
            self._cleanup(device)

    def _handle_message(self, device, msg):
        msg_type = msg.get("type", "")
        msg_id = msg.get("id", 0)

        if msg_type == "ping":
            return {"type": "pong", "id": msg_id}

        if self._on_message:
            return self._on_message(device, msg)
        return None

    def send(self, device, data):
        if isinstance(data, (dict, list)):
            data = json.dumps(data, ensure_ascii=False) + "\n"
        if isinstance(data, str):
            data = data.encode("utf-8")
        if not data.endswith(b"\n"):
            data += b"\n"

        with self._lock:
            entry = self._connections.get(device)
        if not entry:
            logger.warning(f"SPP send: no connection for {device}")
            return

        try:
            entry["sock"].sendall(data)
        except (OSError, ConnectionError) as e:
            logger.error(f"SPP send error {device}: {e}")
            self._cleanup(device)

    def broadcast(self, data):
        with self._lock:
            devices = list(self._connections.keys())
        for device in devices:
            self.send(device, data)

    @dbus.service.method(PROFILE_IFACE, in_signature="o", out_signature="")
    def RequestDisconnection(self, device):
        logger.info(f"SPP disconnect request: {device}")
        self._cleanup(device)

    @dbus.service.method(PROFILE_IFACE, in_signature="", out_signature="")
    def Release(self):
        logger.info("SPP profile release")
        with self._lock:
            for device in list(self._connections.keys()):
                self._cleanup(device)

    def _cleanup(self, device):
        with self._lock:
            entry = self._connections.pop(device, None)
        if entry:
            try:
                entry["sock"].close()
            except OSError:
                pass
            try:
                os.close(entry["fd"])
            except OSError:
                pass
            logger.info(f"SPP connection cleaned up: {device}")
        if self._on_disconnect:
            self._on_disconnect(device)

    @property
    def connected_devices(self):
        with self._lock:
            return list(self._connections.keys())


class SPPServer:

    def __init__(self, bus, adapter_path="/org/bluez/hci0", uuid=SPP_UUID,
                 name="Bluetools SPP", channel=1, on_connect=None,
                 on_disconnect=None, on_message=None):
        self.bus = bus
        self.adapter_path = adapter_path
        self.uuid = uuid
        self.name = name
        self.channel = channel
        self.profile_path = f"/org/bluetools/spp_profile"
        self.profile = SerialProfile(
            bus, self.profile_path, uuid, name, channel,
            on_connect=on_connect, on_disconnect=on_disconnect,
            on_message=on_message,
        )

    def register(self):
        """Register SPP profile with BlueZ."""
        try:
            profile_manager = dbus.Interface(
                self.bus.get_object(BLUEZ_SERVICE, self.adapter_path),
                PROFILE_MANAGER_IFACE,
            )
            profile_manager.RegisterProfile(
                dbus.ObjectPath(self.profile_path),
                self.uuid,
                dbus.Dictionary({}, signature="sv"),
            )
            logger.info(f"SPP profile registered: {self.name}")
        except dbus.exceptions.DBusException as e:
            if "AlreadyExists" in str(e):
                logger.warning("SPP profile already registered")
            else:
                raise

    def unregister(self):
        try:
            profile_manager = dbus.Interface(
                self.bus.get_object(BLUEZ_SERVICE, self.adapter_path),
                PROFILE_MANAGER_IFACE,
            )
            profile_manager.UnregisterProfile(
                dbus.ObjectPath(self.profile_path)
            )
            logger.info("SPP profile unregistered")
        except Exception as e:
            logger.warning(f"Failed to unregister SPP profile: {e}")

    @property
    def profile_obj(self):
        return self.profile
