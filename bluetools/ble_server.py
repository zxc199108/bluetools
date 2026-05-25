import dbus
import dbus.service
import dbus.mainloop.glib
import logging
import json
import os
import threading
from collections import deque

logger = logging.getLogger(__name__)

BLUEZ_SERVICE = "org.bluez"
GATT_MANAGER_IFACE = "org.bluez.GattManager1"
GATT_SERVICE_IFACE = "org.bluez.GattService1"
GATT_CHRC_IFACE = "org.bluez.GattCharacteristic1"
LE_ADVERTISING_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
LE_ADVERTISEMENT_IFACE = "org.bluez.LEAdvertisement1"
DBUS_OM_IFACE = "org.freedesktop.DBus.ObjectManager"
DBUS_PROP_IFACE = "org.freedesktop.DBus.Properties"

SERVICE_UUID = "12345678-1234-1234-1234-123456789abc"

CHAR_DEFS = {
    "wifi_ssid":     ("12345678-1234-1234-1234-123456789001", ["write"]),
    "wifi_password": ("12345678-1234-1234-1234-123456789002", ["write"]),
    "wifi_connect":  ("12345678-1234-1234-1234-123456789003", ["write"]),
    "wifi_status":   ("12345678-1234-1234-1234-123456789004", ["read", "notify"]),
    "wifi_scan":     ("12345678-1234-1234-1234-123456789005", ["write", "notify"]),
    "system_cmd":    ("12345678-1234-1234-1234-123456789006", ["write"]),
    "system_result": ("12345678-1234-1234-1234-123456789007", ["read", "notify"]),
}


class Characteristic(dbus.service.Object):

    def __init__(self, bus, index, uuid, flags, service):
        self.path = f"{service.path}/char{index:04d}"
        self.bus = bus
        self.uuid = uuid
        self.flags = flags
        self.service = service
        self._value = b""
        self._notifying = False
        self._on_write_cb = None
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_CHRC_IFACE: {
                "UUID": self.uuid,
                "Service": dbus.ObjectPath(self.service.path),
                "Value": dbus.Array(bytearray(self._value), signature="y"),
                "Flags": dbus.Array(self.flags, signature="s"),
                "Notifying": self._notifying,
            }
        }

    def set_on_write(self, callback):
        self._on_write_cb = callback

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != GATT_CHRC_IFACE:
            raise dbus.exceptions.DBusException(
                f"Unknown interface: {interface}", name="org.freedesktop.DBus.Error.InvalidArgs"
            )
        return self.get_properties()[GATT_CHRC_IFACE]

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="a{sv}", out_signature="ay")
    def ReadValue(self, options):
        logger.debug(f"ReadValue: {self.uuid} -> {self._value}")
        return dbus.Array(bytearray(self._value), signature="y")

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="aya{sv}", out_signature="")
    def WriteValue(self, value, options):
        if isinstance(value, dbus.Array):
            data = bytes(bytearray(value))
        elif isinstance(value, (bytes, bytearray)):
            data = bytes(value)
        elif isinstance(value, int):
            import os

            try:
                data = os.read(value, 1024)
                os.close(value)
            except OSError:
                data = b""
                logger.warning("Failed to read from fd in WriteValue")
        else:
            data = b""
        logger.debug(f"WriteValue: {self.uuid} <- {data}")
        self._value = data
        if self._on_write_cb:
            self._on_write_cb(data)

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="", out_signature="")
    def StartNotify(self):
        if self._notifying:
            logger.debug(f"Notify already active: {self.uuid}")
            return
        self._notifying = True
        logger.debug(f"Notify started: {self.uuid}")

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="", out_signature="")
    def StopNotify(self):
        if not self._notifying:
            return
        self._notifying = False
        logger.debug(f"Notify stopped: {self.uuid}")

    def notify(self, data):
        if not self._notifying:
            logger.debug(f"Notify skipped (not subscribed): {self.uuid}")
            return
        if isinstance(data, str):
            data = data.encode("utf-8")
        elif not isinstance(data, (bytes, bytearray)):
            data = bytes(data)
        try:
            self.PropertiesChanged(
                GATT_CHRC_IFACE,
                dbus.Dictionary(
                    {"Value": dbus.Array(bytearray(data), signature="y")},
                    signature="sv",
                ),
                dbus.Array([], signature="s"),
            )
        except Exception as e:
            logger.error(f"Notify failed: {e}")

    @dbus.service.signal(DBUS_PROP_IFACE, signature="sa{sv}as")
    def PropertiesChanged(self, interface, changed, invalidated):
        pass


class Service(dbus.service.Object):

    def __init__(self, bus, index, uuid, primary=True):
        self.path = f"/org/bluetools/service{index:04d}"
        self.bus = bus
        self.uuid = uuid
        self.primary = primary
        self.characteristics = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_SERVICE_IFACE: {
                "UUID": self.uuid,
                "Primary": self.primary,
                "Includes": dbus.Array([], signature="o"),
            }
        }

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != GATT_SERVICE_IFACE:
            raise dbus.exceptions.DBusException(
                f"Unknown interface: {interface}",
                name="org.freedesktop.DBus.Error.InvalidArgs",
            )
        return self.get_properties()[GATT_SERVICE_IFACE]

    def add_characteristic(self, characteristic):
        self.characteristics.append(characteristic)


class Application(dbus.service.Object):

    def __init__(self, bus):
        self.path = "/org/bluetools"
        self.bus = bus
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)

    def add_service(self, service):
        self.services.append(service)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_OM_IFACE, out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
        response = {}
        for service in self.services:
            response[dbus.ObjectPath(service.path)] = service.get_properties()
            for chrc in service.characteristics:
                response[dbus.ObjectPath(chrc.path)] = chrc.get_properties()
        return response


class Advertisement(dbus.service.Object):

    def __init__(self, bus, path, name, service_uuids=None):
        self.path = path
        self.bus = bus
        self._name = name
        self._service_uuids = service_uuids or []
        self._include_tx_power = True
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        props = {}
        props["Type"] = dbus.types.String("peripheral", variant_level=1)
        props["LocalName"] = dbus.types.String(self._name, variant_level=1)
        if self._service_uuids:
            props["ServiceUUIDs"] = dbus.types.Array(
                [dbus.types.String(u) for u in self._service_uuids],
                signature="s",
                variant_level=1,
            )
        props["Includes"] = dbus.types.Array(["tx-power"], signature="s")
        return {LE_ADVERTISEMENT_IFACE: props}

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != LE_ADVERTISEMENT_IFACE:
            raise dbus.exceptions.DBusException(
                f"Unknown interface: {interface}",
                name="org.freedesktop.DBus.Error.InvalidArgs",
            )
        return self.get_properties()[LE_ADVERTISEMENT_IFACE]

    @dbus.service.method(LE_ADVERTISEMENT_IFACE, in_signature="", out_signature="")
    def Release(self):
        logger.info("Advertisement released")
        self.remove_from_connection()


class BLEServer:

    def __init__(self, bus, adapter_path="/org/bluez/hci0", name="Bluetools-BLE"):
        self.bus = bus
        self.adapter_path = adapter_path
        self.name = name
        self.app = Application(bus)
        self._advertisement = None
        self._chars = {}
        self._command_queue = deque()
        self._command_event = threading.Event()
        self._running = False
        self._worker = None

    def setup(self, on_wifi_ssid=None, on_wifi_password=None, on_wifi_connect=None,
              on_wifi_scan=None, on_system_cmd=None):
        """Create GATT service and characteristics."""
        service = Service(self.bus, 0, SERVICE_UUID, primary=True)
        self.app.add_service(service)

        for idx, (key, (uuid, flags)) in enumerate(CHAR_DEFS.items()):
            chrc = Characteristic(self.bus, idx, uuid, flags, service)
            service.add_characteristic(chrc)
            self._chars[key] = chrc

        def make_cb(handler):
            def cb(data):
                handler(data)
            return cb

        if on_wifi_ssid:
            self._chars["wifi_ssid"].set_on_write(make_cb(on_wifi_ssid))
        if on_wifi_password:
            self._chars["wifi_password"].set_on_write(make_cb(on_wifi_password))
        if on_wifi_connect:
            self._chars["wifi_connect"].set_on_write(make_cb(on_wifi_connect))
        if on_wifi_scan:
            self._chars["wifi_scan"].set_on_write(make_cb(on_wifi_scan))
        if on_system_cmd:
            self._chars["system_cmd"].set_on_write(make_cb(on_system_cmd))

    def register(self):
        """Register GATT application with BlueZ."""
        adapter = dbus.Interface(
            self.bus.get_object(BLUEZ_SERVICE, self.adapter_path),
            GATT_MANAGER_IFACE,
        )
        adapter.RegisterApplication(
            self.app.get_path(), dbus.Dictionary({}, signature="sv")
        )
        logger.info(f"GATT application registered on {self.adapter_path}")

    def unregister(self):
        try:
            adapter = dbus.Interface(
                self.bus.get_object(BLUEZ_SERVICE, self.adapter_path),
                GATT_MANAGER_IFACE,
            )
            adapter.UnregisterApplication(self.app.get_path())
            logger.info("GATT application unregistered")
        except Exception as e:
            logger.warning(f"Failed to unregister GATT app: {e}")

    def start_advertising(self):
        """Start BLE advertising with proper LEAdvertisement1 object."""
        try:
            ad_path = "/org/bluetools/advertisement"
            self._advertisement = Advertisement(
                self.bus, ad_path, self.name, [SERVICE_UUID]
            )

            adapter = self.bus.get_object(BLUEZ_SERVICE, self.adapter_path)
            ad_manager = dbus.Interface(adapter, LE_ADVERTISING_MANAGER_IFACE)
            ad_manager.RegisterAdvertisement(
                dbus.ObjectPath(ad_path),
                dbus.Dictionary({}, signature="sv"),
            )
            logger.info(f"BLE advertising started: {self.name}")
        except dbus.exceptions.DBusException as e:
            if "AlreadyExists" in str(e):
                logger.warning("Advertisement already registered, trying to re-register...")
                try:
                    ad_manager.UnregisterAdvertisement(dbus.ObjectPath(ad_path))
                    self._advertisement = Advertisement(
                        self.bus, ad_path, self.name, [SERVICE_UUID]
                    )
                    ad_manager.RegisterAdvertisement(
                        dbus.ObjectPath(ad_path),
                        dbus.Dictionary({}, signature="sv"),
                    )
                    logger.info(f"BLE advertising re-registered: {self.name}")
                except Exception as e2:
                    logger.error(f"Failed to re-register advertisement: {e2}")
                    raise
            else:
                raise

    def stop_advertising(self):
        try:
            adapter = self.bus.get_object(BLUEZ_SERVICE, self.adapter_path)
            ad_manager = dbus.Interface(adapter, LE_ADVERTISING_MANAGER_IFACE)
            ad_manager.UnregisterAdvertisement(
                dbus.ObjectPath("/org/bluetools/advertisement")
            )
            self._advertisement = None
            logger.info("BLE advertising stopped")
        except Exception as e:
            logger.warning(f"Failed to stop advertising: {e}")

    def notify_wifi_status(self, data):
        """Send WiFi status via BLE notification."""
        chrc = self._chars.get("wifi_status")
        if chrc:
            chrc.notify(json.dumps(data))

    def notify_wifi_scan(self, data):
        chrc = self._chars.get("wifi_scan")
        if chrc:
            chrc.notify(json.dumps(data))

    def notify_system_result(self, data):
        chrc = self._chars.get("system_result")
        if chrc:
            chrc.notify(json.dumps(data))
