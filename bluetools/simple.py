#!/usr/bin/env python3
"""Raw-socket SPP + bluetoothctl auto-agent + Web UI.  No pexpect needed."""
import socket, subprocess, threading, json, os, time, signal, logging
from http.server import HTTPServer, BaseHTTPRequestHandler

DEVICE_NAME = "Bluetools"
SPP_CHANNEL = 1
WEB_PORT = 5000
PIN_CODE = "1234"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bluetools")


# ═══════════════════════════════════════════════════
#  BLUETOOTHCTL AUTO-AGENT (no D-Bus, no pexpect)
# ═══════════════════════════════════════════════════
def start_dbus_agent():
    """Register BlueZ D-Bus agent in a thread. No external processes."""
    try:
        import dbus, dbus.service, dbus.mainloop.glib
        from gi.repository import GLib
    except ImportError as e:
        logger.error(f"[agent] dbus missing: {e}")
        return

    class _A(dbus.service.Object):
        def __init__(self, bus):
            dbus.service.Object.__init__(self, bus, "/org/bluetools/agent")
        @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
        def Release(self): pass
        @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="s")
        def RequestPinCode(self, device):
            logger.info(f"[agent] pin -> {PIN_CODE}")
            return PIN_CODE
        @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
        def DisplayPinCode(self, device, pincode): pass
        @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="u")
        def RequestPasskey(self, device):
            return dbus.types.UInt32(int(PIN_CODE))
        @dbus.service.method("org.bluez.Agent1", in_signature="ouq", out_signature="")
        def DisplayPasskey(self, device, passkey, entered): pass
        @dbus.service.method("org.bluez.Agent1", in_signature="ou", out_signature="")
        def RequestConfirmation(self, device, passkey): pass
        @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="")
        def RequestAuthorization(self, device): pass
        @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
        def AuthorizeService(self, device, uuid): pass
        @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
        def Cancel(self): pass

    def _run():
        try:
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            bus = dbus.SystemBus()
            _A(bus)
            mgr = dbus.Interface(bus.get_object("org.bluez", "/org/bluez"), "org.bluez.AgentManager1")
            path = dbus.ObjectPath("/org/bluetools/agent")
            try: mgr.UnregisterAgent(path)
            except: pass
            mgr.RegisterAgent(path, "DisplayOnly")
            mgr.RequestDefaultAgent(path)
            logger.info(f"[agent] registered (PIN={PIN_CODE})")
            GLib.MainLoop().run()
        except Exception as e:
            logger.error(f"[agent] {e}")

    t = threading.Thread(target=_run, daemon=True, name="agent")
    t.start()
    time.sleep(0.5)


def init_adapter():
    """bluetoothd handles adapter state via main.conf — nothing to do here."""


# ═══════════════════════════════════════════════════
#  SPP SERVER (raw RFCOMM socket)
# ═══════════════════════════════════════════════════
class SPPServer:
    def __init__(self, channel=1):
        self.channel = channel
        self._sock = None
        self._running = False

    def start(self):
        try:
            subprocess.run(
                ["sdptool", "add", f"--channel={self.channel}", "SP"],
                capture_output=True, timeout=5,
            )
            logger.info(f"[spp] SDP registered ch={self.channel}")
        except Exception as e:
            logger.warning(f"[spp] sdptool: {e}")

        addr = _bt_addr()
        self._sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((addr, self.channel))
        self._sock.listen(5)
        self._running = True
        logger.info(f"[spp] Listening {addr} ch={self.channel}")

        while self._running:
            try:
                self._sock.settimeout(1)
                c, a = self._sock.accept()
                addr_str = f"{a[0]}:{a[1]}"
                logger.info(f"[spp] Connected {addr_str}")
                threading.Thread(target=self._handle, args=(c, addr_str), daemon=True).start()
            except socket.timeout:
                continue
            except OSError:
                break

    def _handle(self, sock, addr):
        buf = b""
        _send(sock, {"type": "ready", "msg": "Bluetools SPP"})
        try:
            while self._running:
                data = sock.recv(4096)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if line:
                        self._process(sock, addr, line)
        except Exception as e:
            logger.error(f"[spp] {addr}: {e}")
        finally:
            sock.close()
            logger.info(f"[spp] Disconnected {addr}")

    def _process(self, sock, addr, raw):
        try:
            line = raw.decode()
        except Exception:
            _send(sock, {"type": "error", "error": "decode fail"})
            return

        try:
            m = json.loads(line)
        except json.JSONDecodeError:
            # Raw shell command
            try:
                r = subprocess.run(line, shell=True, capture_output=True, text=True, timeout=30)
                out = r.stdout
                if r.stderr:
                    out += r.stderr
                _send(sock, {"type": "raw", "output": out or "(no output)"})
            except subprocess.TimeoutExpired:
                _send(sock, {"type": "raw", "output": "timeout"})
            except Exception as e:
                _send(sock, {"type": "raw", "output": str(e)})
            return
        t = m.get("type", "")
        rid = m.get("id", 0)
        logger.info(f"[spp] {t}")

        if t == "ping":
            _send(sock, {"type": "pong", "id": rid})
        elif t == "wifi_scan":
            _send(sock, {"type": "wifi_scan_result", "id": rid, **wifi_scan()})
        elif t == "wifi_connect":
            _send(sock, {"type": "wifi_connect_result", "id": rid, **wifi_connect(m.get("ssid", ""), m.get("password", ""))})
        elif t == "wifi_status":
            _send(sock, {"type": "wifi_status_result", "id": rid, **wifi_status()})
        elif t == "cmd":
            _send(sock, {"type": "cmd_result", "id": rid, **run_cmd(m.get("command", ""), m.get("args", []))})
        else:
            _send(sock, {"type": "error", "error": f"unknown: {t}"})

    def stop(self):
        self._running = False
        if self._sock:
            self._sock.close()


def _send(sock, data):
    try:
        sock.sendall((json.dumps(data, ensure_ascii=False) + "\n").encode())
    except OSError:
        pass


def _bt_addr():
    for line in os.popen("hcitool dev").read().split("\n"):
        p = line.strip().split()
        if len(p) == 2 and ":" in p[1]:
            return p[1]
    return "00:00:00:00:00:00"


# ═══════════════════════════════════════════════════
#  WIFI / CMD helpers
# ═══════════════════════════════════════════════════
def _r(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -1, "", "not found"


def wifi_scan():
    _r(["nmcli", "device", "wifi", "rescan"], 10)
    time.sleep(3)
    code, out, _ = _r(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"], 15)
    nets = []
    for line in out.split("\n"):
        if ":" not in line:
            continue
        parts = line.strip().split(":")
        if len(parts) >= 2:
            nets.append({"ssid": parts[0], "signal": parts[1], "security": parts[2] if len(parts) > 2 else ""})
    return {"success": code == 0, "networks": nets}


def wifi_connect(ssid, pw=""):
    args = ["nmcli", "device", "wifi", "connect", ssid]
    if pw:
        args += ["password", pw]
    code, out, _ = _r(args, 60)
    ip = _get_ip()
    return {"success": code == 0, "ssid": ssid, "ip": ip, "error": out if code else ""}


def wifi_status():
    iface = _wifi_iface()
    if not iface:
        return {"state": "no_wifi", "ssid": "", "ip": ""}
    code, out, _ = _r(["nmcli", "-t", "-f", "GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS", "device", "show", iface], 5)
    state, ssid, ip = "disconnected", "", ""
    for line in out.split("\n"):
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        if k == "GENERAL.STATE":
            state = "connected" if "connected" in v.lower() else "disconnected"
        elif k == "GENERAL.CONNECTION":
            ssid = v
        elif k == "IP4.ADDRESS":
            import re
            m = re.match(r"(\d+\.\d+\.\d+\.\d+)", v)
            if m:
                ip = m.group(1)
    return {"state": state, "ssid": ssid, "ip": ip}


def _wifi_iface():
    code, out, _ = _r(["nmcli", "-t", "-f", "DEVICE,TYPE", "device", "status"], 5)
    for line in out.split("\n"):
        try:
            dev, typ = line.strip().split(":")
            if typ == "wifi":
                return dev
        except ValueError:
            continue
    return ""


def _get_ip():
    iface = _wifi_iface()
    if not iface:
        return ""
    code, out, _ = _r(["nmcli", "-t", "-f", "IP4.ADDRESS", "device", "show", iface], 5)
    import re
    m = re.search(r"(\d+\.\d+\.\d+\.\d+)", out)
    return m.group(1) if m else ""


def run_cmd(command, args=None):
    full = [command] + (list(args) if args else [])
    try:
        r = subprocess.run(full, capture_output=True, text=True, timeout=30)
        return {"success": r.returncode == 0, "output": r.stdout.strip() or r.stderr.strip()}
    except Exception as e:
        return {"success": False, "output": str(e)}


# ═══════════════════════════════════════════════════
#  WEB UI
# ═══════════════════════════════════════════════════
INDEX_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Bluetools</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,sans-serif;background:#0f0f0f;color:#e0e0e0}
.header{background:#1a1a2e;padding:16px 24px;border-bottom:1px solid #2a2a4a;display:flex;justify-content:space-between}
.header h1{font-size:20px;color:#00d4aa}
.container{max-width:900px;margin:0 auto;padding:24px 16px}
.card{background:#1a1a1a;border-radius:12px;padding:20px;margin-bottom:16px;border:1px solid #2a2a2a}
.card h2{font-size:13px;color:#888;margin-bottom:12px;text-transform:uppercase}
.row{display:flex;gap:12px;flex-wrap:wrap}
.stat{flex:1;min-width:120px;background:#111;border-radius:8px;padding:14px;text-align:center}
.stat .label{font-size:11px;color:#666}.stat .value{font-size:20px;font-weight:700}
.green{color:#00d4aa}.yellow{color:#f0a500}.red{color:#e04040}
.btn{padding:10px 20px;border-radius:8px;border:none;font-size:14px;cursor:pointer;font-weight:600}
.btn-primary{background:#00d4aa;color:#000}.btn-danger{background:#e04040;color:#fff}
.btn-outline{background:transparent;border:1px solid #444;color:#aaa}
.btn-outline:hover{border-color:#00d4aa;color:#00d4aa}
.input-group{display:flex;gap:8px;margin-bottom:10px;align-items:center}
.input-group label{min-width:80px;font-size:13px;color:#888}
.input-group input{flex:1;padding:10px 12px;background:#111;border:1px solid #333;border-radius:8px;color:#e0e0e0;font-size:14px}
.network-list{max-height:280px;overflow-y:auto}
.network-item{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid #222}
.network-item .ssid{font-weight:600}.network-item .meta{font-size:12px;color:#666}
.cmd-output{background:#111;border-radius:8px;padding:12px;font-family:monospace;font-size:12px;white-space:pre-wrap;max-height:200px;overflow-y:auto;margin-top:8px}
.toast{position:fixed;top:16px;right:16px;padding:12px 20px;border-radius:8px;font-size:14px;z-index:9999}
.toast.success{background:#00d4aa;color:#000}.toast.error{background:#e04040;color:#fff}
</style>
</head>
<body>
<div class="header"><h1>Bluetools</h1><span style="font-size:12px;color:#666;padding-top:6px">PIN: 1234</span></div>
<div class="container">
<div class="card"><h2>Status</h2><div class="row">
<div class="stat"><div class="label">SPP</div><div class="value green">ch 1</div></div>
<div class="stat"><div class="label">WiFi</div><div class="value" id="wifi-state">--</div></div></div></div>
<div class="card"><h2>WiFi</h2>
<button class="btn btn-outline" onclick="scanWifi()" style="margin-bottom:12px">Scan</button>
<div class="network-list" id="wifi-list"><div style="color:#666">Click Scan</div></div>
<div class="input-group" style="margin-top:12px"><label>SSID</label><input id="wifi-ssid"></div>
<div class="input-group"><label>Password</label><input type="password" id="wifi-pass"></div>
<button class="btn btn-primary" onclick="connectWifi()">Connect</button></div>
<div class="card"><h2>Command</h2>
<div class="input-group"><label>Cmd</label><input id="cmd-input" placeholder="uptime"><button class="btn btn-primary" onclick="execCmd()">Run</button></div>
<div class="cmd-output" id="cmd-output">--</div></div>
</div>
<div id="toast"></div>
<script>
var B=location.origin;
function toast(m,c){c=c||'success';var e=document.getElementById('toast');e.className='toast '+c;e.textContent=m;setTimeout(function(){e.className='toast';e.textContent=''},3000)}
async function api(m,u,b){try{var r=await fetch(B+u,{method:m,headers:b?{'Content-Type':'application/json'}:{},body:b?JSON.stringify(b):null});return await r.json()}catch(e){return{error:''+e}}}
async function scanWifi(){var l=document.getElementById('wifi-list');l.innerHTML='<div style="color:#666">Scanning...</div>';var r=await api('POST','/api/wifi/scan');if(r.error||!r.success){l.innerHTML='<div style="color:#e04040">'+(r.error||'fail')+'</div>';return}if(!r.networks.length){l.innerHTML='<div style="color:#666">None</div>';return}l.innerHTML=r.networks.map(function(n){return'<div class="network-item"><div><div class="ssid">'+(n.ssid||'hidden')+'</div><div class="meta">'+n.signal+' '+n.security+'</div></div><button class="btn btn-outline" onclick="qc(\''+n.ssid.replace(/'/g,"\\'")+'\')">Connect</button></div>'}).join('')}
function qc(s){document.getElementById('wifi-ssid').value=s;document.getElementById('wifi-pass').focus()}
async function connectWifi(){var s=document.getElementById('wifi-ssid').value.trim(),p=document.getElementById('wifi-pass').value;if(!s)return toast('SSID?','error');toast('Connecting...');var r=await api('POST','/api/wifi/connect',{ssid:s,password:p});if(r.success)toast('OK IP:'+(r.ip||'?'));else toast(r.error||'fail','error')}
async function execCmd(){var c=document.getElementById('cmd-input').value.trim();if(!c)return;document.getElementById('cmd-output').textContent='...';var r=await api('POST','/api/cmd',{command:c,args:[]});document.getElementById('cmd-output').textContent=r.output||r.error||'done'}
function refresh(){api('GET','/api/status').then(function(r){document.getElementById('wifi-state').textContent=r.wifi||'--';document.getElementById('wifi-state').className='value '+(r.wifi=='connected'?'green':'yellow')})}
refresh();setInterval(refresh,5000)
</script>
</body>
</html>"""


class WebHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, data, code=200):
        b = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _read(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n).decode()) if n else {}

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            b = INDEX_HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif self.path == "/api/status":
            self._json({"wifi": wifi_status().get("state", "unknown")})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        try:
            d = self._read()
        except Exception:
            d = {}
        if self.path == "/api/wifi/scan":
            self._json(wifi_scan())
        elif self.path == "/api/wifi/connect":
            self._json(wifi_connect(d.get("ssid", ""), d.get("password", "")))
        elif self.path == "/api/wifi/disconnect":
            self._json({"success": True})
        elif self.path == "/api/cmd":
            self._json(run_cmd(d.get("command", ""), d.get("args", [])))
        else:
            self._json({"error": "not found"}, 404)


# ═══════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════
def main():
    logger.info(f"=== Bluetools | PIN={PIN_CODE} | SPP ch={SPP_CHANNEL} | Web={WEB_PORT} ===")

    init_adapter()

    # Start pairing agent as subprocess
    agent_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent.py")
    subprocess.Popen(["/usr/bin/python3", agent_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.5)
    logger.info("[agent] pairing agent started")

    spp = SPPServer(channel=SPP_CHANNEL)
    threading.Thread(target=spp.start, daemon=True, name="spp").start()

    httpd = HTTPServer(("0.0.0.0", WEB_PORT), WebHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True, name="web").start()
    logger.info(f"Ready: Web http://0.0.0.0:{WEB_PORT} | SPP ch={SPP_CHANNEL} | PIN={PIN_CODE}")

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *a: stop.set())
    signal.signal(signal.SIGTERM, lambda *a: stop.set())
    stop.wait()
    spp.stop()
    httpd.shutdown()


if __name__ == "__main__":
    main()
