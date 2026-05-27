#!/usr/bin/env python3
"""Minimal BlueZ pairing agent.  Standalone, no deps beyond python3-dbus."""
import dbus, dbus.service, dbus.mainloop.glib
from gi.repository import GLib

PIN = "1234"
AGENT_PATH = "/org/bluetools/agent"

class Agent(dbus.service.Object):
    def __init__(self, bus):
        dbus.service.Object.__init__(self, bus, AGENT_PATH)

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        print(f"[agent] PIN -> {PIN}")
        return PIN

    @dbus.service.method("org.bluez.Agent1", in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        print(f"[agent] confirm {passkey} -> accept")

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        print(f"[agent] authorize -> accept")

    @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        print(f"[agent] auth service {uuid} -> accept")

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Cancel(self): pass

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Release(self): pass

    @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
    def DisplayPinCode(self, device, pincode):
        print(f"[agent] display pin: {pincode}")

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        return dbus.UInt32(int(PIN))

    @dbus.service.method("org.bluez.Agent1", in_signature="ouq", out_signature="")
    def DisplayPasskey(self, device, passkey, entered):
        print(f"[agent] display passkey: {passkey}")

    @dbus.service.method("org.freedesktop.DBus.Properties",
                         in_signature="s", out_signature="a{sv}")
    def GetAll(self, iface):
        return {}

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
bus = dbus.SystemBus()
agent = Agent(bus)

mgr = dbus.Interface(bus.get_object("org.bluez", "/org/bluez"),
                     "org.bluez.AgentManager1")
try:
    mgr.UnregisterAgent(dbus.ObjectPath(AGENT_PATH))
except:
    pass

mgr.RegisterAgent(dbus.ObjectPath(AGENT_PATH), "NoInputNoOutput")
mgr.RequestDefaultAgent(dbus.ObjectPath(AGENT_PATH))
print(f"[agent] registered (PIN={PIN})")

GLib.MainLoop().run()
