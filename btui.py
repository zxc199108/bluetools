#!/usr/bin/env python3
"""
Android Bluetooth SPP → Web UI bridge for Termux.
Run:  python3 btui.py
Open: http://localhost:8080 in Android browser
"""
import socket
import json
import subprocess
import threading
import time
import os
import re
from http.server import HTTPServer, BaseHTTPRequestHandler

BOARD_NAME = "Bluetools"
CHANNEL = 1
WEB_PORT = 8080

# ──── HTML ────
UI = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,user-scalable=no">
<title>Bluetools</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,sans-serif;background:#0a0a0a;color:#ddd;min-height:100vh}
.top{background:#111;padding:14px 16px;display:flex;align-items:center;gap:10px;justify-content:space-between}
.top h1{font-size:18px;color:#00d4aa}
.top .status{font-size:11px;padding:4px 10px;border-radius:12px;background:#222}
.top .status.on{background:#003a30;color:#00d4aa}
.top .status.off{background:#3a0000;color:#e04040}
.content{padding:12px}
.card{background:#161616;border-radius:10px;padding:14px;margin-bottom:10px;border:1px solid #222}
.card h2{font-size:12px;color:#666;margin-bottom:8px;text-transform:uppercase;letter-spacing:1px}
.row{display:flex;gap:8px;align-items:center}
.btn{flex:1;padding:11px;border-radius:8px;border:none;font-size:13px;font-weight:600;cursor:pointer}
.btn-go{background:#00d4aa;color:#000}.btn-go:active{background:#00f0c0}
.btn-warn{background:#e04040;color:#fff}.btn-warn:active{background:#f05050}
.btn-out{background:transparent;border:1px solid #333;color:#999}
.input-row{display:flex;gap:6px;margin-bottom:8px}
input,select{flex:1;padding:10px;background:#0a0a0a;border:1px solid #333;border-radius:6px;color:#ddd;font-size:14px}
input:focus{border-color:#00d4aa;outline:none}
.list{max-height:260px;overflow:auto}
.item{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid #1a1a1a;font-size:14px}
.item .ssid{font-weight:600}.item .sig{font-size:11px;color:#666}
.output{background:#0a0a0a;border-radius:6px;padding:10px;font-family:monospace;font-size:12px;max-height:150px;overflow:auto;white-space:pre-wrap}
.toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#00d4aa;color:#000;padding:8px 16px;border-radius:20px;font-size:13px;z-index:99;transition:all .3s}
.modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.8);z-index:98;align-items:center;justify-content:center}
.modal.show{display:flex}
.modal-inner{background:#161616;border-radius:12px;padding:20px;width:90%;max-width:360px;text-align:center}
.modal-inner h3{margin-bottom:12px}.modal-inner .key{font-size:36px;font-weight:700;color:#00d4aa;margin:8px 0}
</style>
</head>
<body>
<div class="top">
  <h1>Bluetools</h1>
  <span class="status off" id="conn-status">offline</span>
</div>
<div id="toast"></div>

<div class="content">
  <div class="card" id="pair-card">
    <h2>Connection</h2>
    <div class="input-row"><input id="mac-input" placeholder="Board MAC (auto-detect if empty)"></div>
    <div class="row"><button class="btn btn-go" onclick="connect()">Connect</button><button class="btn btn-out" onclick="disconnect()">Disconnect</button></div>
  </div>

  <div class="card" id="wifi-card" style="display:none">
    <h2>WiFi Control</h2>
    <button class="btn btn-out" onclick="scanWifi()" style="width:100%;margin-bottom:8px">Scan Networks</button>
    <div class="list" id="wifi-list"></div>
    <div class="input-row" style="margin-top:8px"><input id="wifi-ssid" placeholder="SSID"></div>
    <div class="input-row"><input type="password" id="wifi-pass" placeholder="Password"></div>
    <button class="btn btn-go" onclick="connectWifi()" style="width:100%">Connect WiFi</button>
  </div>

  <div class="card" id="cmd-card" style="display:none">
    <h2>Command</h2>
    <div class="input-row"><input id="cmd-input" placeholder="uptime"><button class="btn btn-go" onclick="execCmd()">Run</button></div>
    <div class="output" id="cmd-output">Output here...</div>
  </div>
</div>

<script>
var BASE=location.origin,connected=false;
function toast(m){var e=document.getElementById('toast');e.textContent=m;e.style.opacity=1;setTimeout(function(){e.style.opacity=0},2000)}
async function api(path,body){try{var r=await fetch(BASE+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});return await r.json()}catch(e){return{error:''+e}}}
async function connect(){var mac=document.getElementById('mac-input').value.trim();var r=await api('/api/connect',{mac:mac});if(r.connected){connected=true;document.getElementById('conn-status').textContent='online';document.getElementById('conn-status').className='status on';document.getElementById('wifi-card').style.display='';document.getElementById('cmd-card').style.display='';document.getElementById('pair-card').style.display='none';toast('Connected '+r.mac)}else{toast('Failed: '+(r.error||'?'))}}
async function disconnect(){await api('/api/disconnect');connected=false;document.getElementById('conn-status').textContent='offline';document.getElementById('conn-status').className='status off';document.getElementById('wifi-card').style.display='none';document.getElementById('cmd-card').style.display='none';document.getElementById('pair-card').style.display='';toast('Disconnected')}
async function scanWifi(){var l=document.getElementById('wifi-list');l.innerHTML='Scanning...';var r=await api('/api/wifi/scan');if(r.networks)l.innerHTML=r.networks.map(function(n){return'<div class="item"><div><div class="ssid">'+(n.ssid||'hidden')+'</div><div class="sig">'+n.signal+'</div></div><button class="btn btn-out" onclick="fillSSID(\''+n.ssid.replace(/'/g,"\\\\'")+'\')">Fill</button></div>'}).join('');else toast('Scan failed')}
function fillSSID(s){document.getElementById('wifi-ssid').value=s;document.getElementById('wifi-pass').focus()}
async function connectWifi(){var s=document.getElementById('wifi-ssid').value.trim(),p=document.getElementById('wifi-pass').value;if(!s)return toast('Enter SSID');var r=await api('/api/wifi/connect',{ssid:s,password:p});toast(r.success?'Connected! IP:'+(r.ip||'?'):r.error||'Failed')}
async function execCmd(){var c=document.getElementById('cmd-input').value.trim();if(!c)return;document.getElementById('cmd-output').textContent='Running...';var r=await api('/api/cmd',{command:c,args:[]});document.getElementById('cmd-output').textContent=r.output||r.error||'done'}
</script>
</body>
</html>"""


# ──── SPP Client ────
class SPPClient:
    def __init__(self):
        self.sock = None
        self._lock = threading.Lock()

    def scan(self):
        try:
            out = subprocess.check_output(["hcitool", "scan"], text=True, timeout=12)
            for line in out.split("\n"):
                parts = line.strip().split("\t") if "\t" in line else line.strip().split(None, 1)
                if len(parts) >= 2 and BOARD_NAME in parts[1]:
                    return parts[0]
        except Exception:
            pass
        return None

    def connect(self, mac=None):
        with self._lock:
            if self.sock:
                try: self.sock.close()
                except: pass
            if not mac:
                mac = self.scan()
            if not mac:
                return False, "device not found"
            try:
                self.sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
                self.sock.settimeout(8)
                self.sock.connect((mac, CHANNEL))
                return True, mac
            except Exception as e:
                self.sock = None
                return False, str(e)

    def send(self, msg, timeout=8):
        with self._lock:
            if not self.sock:
                return {"error": "not connected"}
            try:
                data = (json.dumps(msg) + "\n").encode()
                self.sock.sendall(data)
                self.sock.settimeout(timeout)
                buf = b""
                while True:
                    d = self.sock.recv(4096)
                    if not d:
                        break
                    buf += d
                    if b"\n" in buf:
                        break
                line = buf.decode().strip().split("\n")[0]
                return json.loads(line)
            except socket.timeout:
                return {"error": "timeout"}
            except Exception as e:
                self.sock = None
                return {"error": str(e)}

    def close(self):
        with self._lock:
            if self.sock:
                try: self.sock.close()
                except: pass
            self.sock = None


spp = SPPClient()


# ──── HTTP Server ────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _json(self, data, code=200):
        b = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _read(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n).decode()) if n else {}

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            b = UI.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

    def do_POST(self):
        try: d = self._read()
        except: d = {}

        if self.path == "/api/connect":
            mac = d.get("mac", "").strip() or None
            ok, result = spp.connect(mac)
            if ok:
                self._json({"connected": True, "mac": result or "ok"})
            else:
                self._json({"connected": False, "error": result})

        elif self.path == "/api/disconnect":
            spp.close()
            self._json({"success": True})

        elif self.path == "/api/wifi/scan":
            r = spp.send({"type": "wifi_scan"})
            self._json(r)

        elif self.path == "/api/wifi/connect":
            r = spp.send({
                "type": "wifi_connect",
                "ssid": d.get("ssid", ""),
                "password": d.get("password", ""),
            })
            self._json(r)

        elif self.path == "/api/cmd":
            r = spp.send({
                "type": "cmd",
                "command": d.get("command", ""),
                "args": d.get("args", []),
            })
            self._json(r)

        elif self.path == "/api/ping":
            r = spp.send({"type": "ping"})
            self._json(r)

        else:
            self._json({"error": "not found"}, 404)


def main():
    print(f"=== Bluetools Android UI ===")
    print(f"Open: http://localhost:{WEB_PORT}")
    print("")

    httpd = HTTPServer(("127.0.0.1", WEB_PORT), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        spp.close()
        httpd.shutdown()


if __name__ == "__main__":
    main()
