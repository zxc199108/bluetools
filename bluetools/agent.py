import dbus
import dbus.service
import logging
import threading
import time
import os

logger = logging.getLogger(__name__)

AGENT_IFACE = "org.bluez.Agent1"
AGENT_MANAGER_IFACE = "org.bluez.AgentManager1"


class Rejected(dbus.DBusException):
    _dbus_error_name = "org.bluez.Error.Rejected"


class AutoPairAgent(dbus.service.Object):

    def __init__(self, bus, path="/org/bluetools/agent",
                 capability="DisplayOnly", pin_code="1234",
                 timeout=120, auto_accept=True):
        self.bus = bus
        self.path = path
        self._capability = capability
        self._pin_code = pin_code
        self._timeout = timeout
        self._auto_accept = auto_accept
        self._lock = threading.Lock()
        self._pending = {}
        self._next_id = 0
        dbus.service.Object.__init__(self, bus, self.path)

    @property
    def capability(self):
        return self._capability

    def _wait_or_auto(self, device, passkey, kind="confirm"):
        if self._auto_accept:
            logger.info(f"[AUTO] {kind} {device[-8:]} passkey={passkey}")
            return

        rid = None
        with self._lock:
            self._next_id += 1
            rid = self._next_id
            self._pending[rid] = {
                "id": rid,
                "device": str(device),
                "device_short": str(device)[-17:],
                "passkey": int(passkey) if passkey is not None else 0,
                "kind": kind,
                "event": threading.Event(),
                "accepted": False,
                "time": time.time(),
            }

        logger.info(f"[WAIT] {kind} {device[-8:]} passkey={passkey} id={rid}")
        ok = self._pending[rid]["event"].wait(self._timeout)

        with self._lock:
            entry = self._pending.pop(rid, None)

        if not ok or not (entry and entry["accepted"]):
            logger.info(f"[REJECT] {kind} {device[-8:]}")
            raise Rejected("User rejected or timeout")

        logger.info(f"[ACCEPT] {kind} {device[-8:]}")

    def get_pending(self):
        with self._lock:
            return list(self._pending.values())

    def accept(self, rid):
        with self._lock:
            entry = self._pending.get(rid)
            if entry:
                entry["accepted"] = True
                entry["event"].set()
                return True
        return False

    def reject(self, rid):
        with self._lock:
            entry = self._pending.get(rid)
            if entry:
                entry["accepted"] = False
                entry["event"].set()
                return True
        return False

    def set_auto_accept(self, auto):
        self._auto_accept = auto
        logger.info(f"Auto-accept: {auto}")

    # --- 配对阶段 ---

    @dbus.service.method(AGENT_IFACE, in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        logger.info(f"[PIN] RequestPinCode {device[-8:]}: returning {self._pin_code}")
        self._wait_or_auto(device, None, "pincode")
        return self._pin_code

    @dbus.service.method(AGENT_IFACE, in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        pk = int(self._pin_code)
        logger.info(f"[PASSKEY] RequestPasskey {device[-8:]}: returning {pk}")
        self._wait_or_auto(device, pk, "passkey")
        return dbus.types.UInt32(pk)

    @dbus.service.method(AGENT_IFACE, in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        logger.info(f"[CONFIRM] RequestConfirmation {device[-8:]} passkey={passkey}")
        self._wait_or_auto(device, passkey, "confirm")

    @dbus.service.method(AGENT_IFACE, in_signature="ouq", out_signature="")
    def DisplayPasskey(self, device, passkey, entered):
        logger.info(f"[DISPLAY] DisplayPasskey {device[-8:]} key={passkey} entered={entered}")
        if self._auto_accept:
            return
        self._wait_or_auto(device, passkey, "display_passkey")

    @dbus.service.method(AGENT_IFACE, in_signature="os", out_signature="")
    def DisplayPinCode(self, device, pincode):
        logger.info(f"[DISPLAY_PIN] DisplayPinCode {device[-8:]} pin={pincode}")
        if self._auto_accept:
            return
        self._wait_or_auto(device, pincode, "display_pin")

    # --- 授权阶段 (post-pairing) ---

    @dbus.service.method(AGENT_IFACE, in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        logger.info(f"[AUTH] RequestAuthorization {device[-8:]} -> accept")
        return

    @dbus.service.method(AGENT_IFACE, in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        logger.info(f"[AUTH] AuthorizeService {device[-8:]} uuid={uuid[:8]}... -> accept")
        return

    @dbus.service.method(AGENT_IFACE, in_signature="", out_signature="")
    def Cancel(self):
        logger.info("[CANCEL] Operation cancelled")
        with self._lock:
            for rid in list(self._pending.keys()):
                entry = self._pending.get(rid)
                if entry:
                    entry["accepted"] = False
                    entry["event"].set()
            self._pending.clear()

    @dbus.service.method(AGENT_IFACE, in_signature="", out_signature="")
    def Release(self):
        logger.info("[RELEASE] Agent released")
        self.Cancel()

    # --- 注册 ---

    def register(self):
        manager = dbus.Interface(
            self.bus.get_object("org.bluez", "/org/bluez"),
            AGENT_MANAGER_IFACE,
        )
        try:
            manager.UnregisterAgent(dbus.ObjectPath(self.path))
        except dbus.exceptions.DBusException:
            pass
        manager.RegisterAgent(
            dbus.ObjectPath(self.path), self._capability
        )
        manager.RequestDefaultAgent(dbus.ObjectPath(self.path))
        logger.info(f"[READY] Agent: {self._capability} pin={self._pin_code} auto={self._auto_accept}")

    def unregister(self):
        try:
            manager = dbus.Interface(
                self.bus.get_object("org.bluez", "/org/bluez"),
                AGENT_MANAGER_IFACE,
            )
            manager.UnregisterAgent(dbus.ObjectPath(self.path))
            logger.info("Agent unregistered")
        except Exception as e:
            logger.warning(f"Failed to unregister agent: {e}")
