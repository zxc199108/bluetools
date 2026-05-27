#!/usr/bin/env python3
"""
HCI controller via raw sockets + ioctl() + mgmt API.
Zero external tool dependency (no btmgmt, hciconfig, bluetoothctl, D-Bus).
"""
import socket, struct, fcntl, select, threading, time, logging

logger = logging.getLogger(__name__)

# ─── ioctl constants ───
HCIDEVUP   = 0x400448c9
HCIDEVDOWN = 0x400448ca
HCIGETDEVINFO = 0x800448d3
HCIGETCONNINFO = 0x800448d8
HCISETSCAN   = 0x400448cb
HCISETAUTH   = 0x400448cc
HCISETENCRYPT = 0x400448cd
HCISETPTYPE  = 0x400448ce
HCISETLINKPOL = 0x400448cf
HCISETLINKMODE = 0x400448d0
HCISETNAME   = 0x400448d1

SCAN_DISABLED = 0x00
SCAN_INQUIRY  = 0x01
SCAN_PAGE     = 0x02

# ─── mgmt constants ───
HCI_CHANNEL_CONTROL = 3
MGMT_INDEX_NONE = 0xFFFF

MGMT_OP_SET_POWERED       = 0x0005
MGMT_OP_SET_DISCOVERABLE  = 0x0006
MGMT_OP_SET_CONNECTABLE   = 0x0007
MGMT_OP_SET_BONDABLE      = 0x0015
MGMT_OP_SET_SSP           = 0x0019
MGMT_OP_SET_IO_CAPABILITY = 0x001B
MGMT_OP_SET_LOCAL_NAME    = 0x0023
MGMT_EV_CMD_COMPLETE      = 0x0001

def _hci_devid():
    """Get first available HCI device ID."""
    for i in range(4):
        try:
            s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
            buf = struct.pack('H', i) + b'\x00' * (8 + 6 + 3 + 2 + 2 + 8 + 8 + 4)
            fcntl.ioctl(s.fileno(), HCIGETDEVINFO, buf)
            s.close()
            return i
        except OSError:
            s.close()
            continue
    return 0


def _mgmt_socket():
    """Open mgmt control socket (bound to HCI_CHANNEL_CONTROL with HCI_DEV_NONE)."""
    sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
    addr = struct.pack("=HHH", socket.AF_BLUETOOTH, 0xFFFF, HCI_CHANNEL_CONTROL)
    sock.bind(addr)
    return sock


def _mgmt_send(sock, opcode, devid, params=b''):
    """Send a mgmt command to specific device."""
    hdr = struct.pack('<HHH', opcode, devid, len(params))
    packet = hdr + params
    target = struct.pack("=HHH", socket.AF_BLUETOOTH, devid, HCI_CHANNEL_CONTROL)
    try:
        sock.sendto(packet, target)
    except OSError as e:
        logger.error(f"[mgmt] send failed: {e}")
        return False

    # Read response
    r, _, _ = select.select([sock], [], [], 2.0)
    if r:
        data = sock.recv(1024)
        if len(data) >= 6:
            ev_opcode, ev_idx, ev_len = struct.unpack('<HHH', data[:6])
            if ev_opcode == MGMT_EV_CMD_COMPLETE and ev_len >= 3:
                status = data[6]
                return status == 0
    return False


class HCI:
    """Raw HCI + mgmt controller."""

    def __init__(self):
        self._devid = _hci_devid()

    def power_on(self):
        try:
            s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
            fcntl.ioctl(s.fileno(), HCIDEVUP, self._devid)
            s.close()
            logger.info("[hci] powered on")
        except OSError as e:
            logger.warning(f"[hci] power on failed: {e}")

    def power_off(self):
        try:
            s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
            fcntl.ioctl(s.fileno(), HCIDEVDOWN, self._devid)
            s.close()
        except OSError:
            pass

    def set_name(self, name):
        buf = name.encode()[:248]
        buf += b'\x00' * (248 - len(buf))
        try:
            s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
            fcntl.ioctl(s.fileno(), HCISETNAME, buf)
            s.close()
        except OSError:
            pass

    def set_scan(self, scan_mode):
        try:
            s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
            fcntl.ioctl(s.fileno(), HCISETSCAN, struct.pack('B', scan_mode))
            s.close()
        except OSError:
            pass

    def set_auth(self, enabled):
        try:
            s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
            fcntl.ioctl(s.fileno(), HCISETAUTH, struct.pack('I', 1 if enabled else 0))
            s.close()
        except OSError:
            pass

    def mgmt_ssp(self, on):
        s = _mgmt_socket()
        ok = _mgmt_send(s, MGMT_OP_SET_SSP, self._devid, struct.pack('B', 1 if on else 0))
        s.close()
        logger.info(f"[hci] SSP {'on' if on else 'off'} {'OK' if ok else 'FAIL'}")
        return ok

    def mgmt_io_cap(self, cap):
        s = _mgmt_socket()
        ok = _mgmt_send(s, MGMT_OP_SET_IO_CAPABILITY, self._devid, struct.pack('B', cap))
        s.close()
        logger.info(f"[hci] IO cap={cap} {'OK' if ok else 'FAIL'}")
        return ok

    def mgmt_pairable(self, on):
        s = _mgmt_socket()
        ok = _mgmt_send(s, MGMT_OP_SET_BONDABLE, self._devid, struct.pack('B', 1 if on else 0))
        s.close()
        logger.info(f"[hci] bondable {'on' if on else 'off'} {'OK' if ok else 'FAIL'}")
        return ok

    def mgmt_connectable(self, on):
        s = _mgmt_socket()
        ok = _mgmt_send(s, MGMT_OP_SET_CONNECTABLE, self._devid, struct.pack('B', 1 if on else 0))
        s.close()
        return ok

    def mgmt_discoverable(self, on):
        s = _mgmt_socket()
        ok = _mgmt_send(s, MGMT_OP_SET_DISCOVERABLE, self._devid,
                        struct.pack('BB', 1 if on else 0, 0))
        s.close()
        return ok

    def setup(self, name="Bluetools", ssp=False, io_cap=0):
        """Full setup: power on, set name, SSP, IO cap, pairable, discoverable."""
        # Power off first to reset, then power on
        try:
            s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
            fcntl.ioctl(s.fileno(), HCIDEVDOWN, self._devid)
            s.close()
        except OSError:
            pass
        time.sleep(0.3)
        self.power_on()
        time.sleep(0.3)
        self.set_name(name)
        self.mgmt_ssp(ssp)
        self.mgmt_io_cap(io_cap)
        self.mgmt_pairable(True)
        self.mgmt_connectable(True)
        self.mgmt_discoverable(True)
        self.set_scan(SCAN_PAGE | SCAN_INQUIRY)  # page + inquiry = piscan
