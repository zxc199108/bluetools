import json
import logging
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

logger = logging.getLogger(__name__)

INDEX_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Bluetools</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#0f0f0f;color:#e0e0e0;min-height:100vh}
.header{background:#1a1a2e;padding:16px 24px;border-bottom:1px solid #2a2a4a;display:flex;justify-content:space-between;align-items:center}
.header h1{font-size:20px;color:#00d4aa}
.container{max-width:900px;margin:0 auto;padding:24px 16px}
.card{background:#1a1a1a;border-radius:12px;padding:20px 24px;margin-bottom:16px;border:1px solid #2a2a2a}
.card h2{font-size:13px;color:#888;margin-bottom:14px;text-transform:uppercase;letter-spacing:1px}
.row{display:flex;gap:12px;flex-wrap:wrap}
.stat{flex:1;min-width:130px;background:#111;border-radius:8px;padding:14px;text-align:center}
.stat .label{font-size:11px;color:#666;margin-bottom:4px}
.stat .value{font-size:20px;font-weight:700}
.green{color:#00d4aa}.yellow{color:#f0a500}.red{color:#e04040}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600}
.badge.green{background:#003a30;color:#00d4aa}.badge.red{background:#3a0000;color:#e04040}
.btn{padding:10px 20px;border-radius:8px;border:none;font-size:14px;cursor:pointer;font-weight:600}
.btn-primary{background:#00d4aa;color:#000}.btn-primary:hover{background:#00f0c0}
.btn-danger{background:#e04040;color:#fff}.btn-danger:hover{background:#f05050}
.btn-success{background:#00aa55;color:#fff}.btn-success:hover{background:#00cc66}
.btn-outline{background:transparent;border:1px solid #444;color:#aaa}
.btn-outline:hover{border-color:#00d4aa;color:#00d4aa}
.input-group{display:flex;gap:8px;margin-bottom:10px;align-items:center}
.input-group label{min-width:80px;font-size:13px;color:#888}
.input-group input,.input-group select{flex:1;padding:10px 12px;background:#111;border:1px solid #333;border-radius:8px;color:#e0e0e0;font-size:14px}
.input-group input:focus,.input-group select:focus{border-color:#00d4aa;outline:none}
.network-list{max-height:300px;overflow-y:auto}
.network-item{display:flex;justify-content:space-between;align-items:center;padding:12px 0;border-bottom:1px solid #222}
.network-item .ssid{font-weight:600}.network-item .meta{font-size:12px;color:#666}
.cmd-output{background:#111;border-radius:8px;padding:12px;font-family:monospace;font-size:12px;white-space:pre-wrap;max-height:200px;overflow-y:auto;margin-top:8px}
.toast{position:fixed;top:16px;right:16px;padding:12px 20px;border-radius:8px;font-size:14px;z-index:9999;animation:slideIn .3s}
.toast.success{background:#00d4aa;color:#000}.toast.error{background:#e04040;color:#fff}
@keyframes slideIn{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}
.modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9998;justify-content:center;align-items:center}
.modal.show{display:flex}
.modal-content{background:#1a1a1a;border-radius:16px;padding:24px;max-width:420px;width:90%;border:1px solid #2a2a2a;text-align:center}
.modal-content h3{margin-bottom:8px}
.modal-content .passkey{font-size:48px;font-weight:700;color:#00d4aa;letter-spacing:8px;margin:16px 0}
.modal-content .device{font-size:13px;color:#666;margin-bottom:20px}
.modal-content .btns{display:flex;gap:12px;justify-content:center}
.toast-container{position:fixed;top:16px;right:16px;z-index:10000}
.flex-between{display:flex;justify-content:space-between;align-items:center}
#pair-popup .countdown{font-size:12px;color:#666;margin-top:8px}
</style>
</head>
<body>
<div class="header"><h1>Bluetools</h1></div>
<div class="container">

<div class="card">
<h2>System</h2>
<div class="row">
<div class="stat"><div class="label">Bluetooth</div><div class="value green" id="bt-state">--</div></div>
<div class="stat"><div class="label">Pair Mode</div><div class="value" id="pair-mode">--</div></div>
<div class="stat"><div class="label">WiFi</div><div class="value" id="wifi-state">--</div></div>
<div class="stat"><div class="label">Agent</div><div class="value yellow" id="agent-mode">--</div></div>
</div>
</div>

<div class="card">
<div class="flex-between"><h2>Bluetooth Pairing</h2><span id="auto-badge" class="badge">manual</span></div>
<div style="margin-top:8px">
<div class="input-group"><label>PIN</label><input type="text" id="pin-input" value="1234" maxlength="16"><button class="btn btn-primary" onclick="setPin()">Apply</button></div>
<div class="input-group"><label>Mode</label><select id="cap-select"><option value="NoInputNoOutput">NoInputNoOutput</option><option value="DisplayOnly" selected>DisplayOnly</option><option value="KeyboardDisplay">KeyboardDisplay</option></select><button class="btn btn-primary" onclick="setCapability()">Apply</button></div>
<div style="display:flex;gap:8px;margin-top:4px">
<button class="btn btn-outline" id="auto-on-btn" onclick="setAutoAccept(true)">Auto Accept ON</button>
<button class="btn btn-outline" id="auto-off-btn" onclick="setAutoAccept(false)">Manual Confirm</button>
<button class="btn btn-outline" id="restart-btn" onclick="restartService()" style="display:none">Restart Service</button>
</div>
</div>
</div>

<div class="card">
<div class="flex-between"><h2>WiFi</h2><button class="btn btn-outline" onclick="scanWifi()">Scan</button></div>
<div class="network-list" id="wifi-list"><div style="color:#666;padding:12px 0">Click Scan</div></div>
<div class="input-group" style="margin-top:12px"><label>SSID</label><input type="text" id="wifi-ssid"></div>
<div class="input-group"><label>Password</label><input type="password" id="wifi-pass"></div>
<button class="btn btn-primary" onclick="connectWifi()">Connect</button>
</div>

<div class="card">
<div class="flex-between"><h2>System Command</h2></div>
<div class="input-group" style="margin-top:8px"><label>Command</label><input type="text" id="cmd-input" placeholder="uptime"><button class="btn btn-primary" onclick="execCmd()">Run</button></div>
<div class="cmd-output" id="cmd-output">Output here...</div>
</div>

</div>

<!-- Pairing modal -->
<div class="modal" id="pair-popup">
<div class="modal-content">
<h3>Bluetooth Pairing Request</h3>
<div class="device" id="popup-device"></div>
<div class="passkey" id="popup-passkey"></div>
<div class="countdown" id="popup-countdown"></div>
<div class="btns">
<button class="btn btn-danger" style="padding:14px 40px;font-size:16px" onclick="rejectPair()">Reject</button>
<button class="btn btn-success" style="padding:14px 40px;font-size:16px" onclick="acceptPair()">Accept</button>
</div>
</div>
</div>

<div class="toast-container" id="toast-container"></div>

<script>
var B=location.origin;
var currentReqId=null;
var popupTimeout=null;

function toast(m,c){c=c||'success';var d=document.getElementById('toast-container'),e=document.createElement('div');e.className='toast '+c;e.textContent=m;d.appendChild(e);setTimeout(function(){e.remove()},2500)}

async function api(m,u,b){try{var r=await fetch(B+u,{method:m,headers:b?{'Content-Type':'application/json'}:{},body:b?JSON.stringify(b):null});return await r.json()}catch(e){return{error:e.message}}}

// ── config ──
async function loadConfig(){var r=await api('GET','/api/config');if(r.error)return;document.getElementById('pin-input').value=r.pin_code||'1234';document.getElementById('cap-select').value=r.capability||'DisplayOnly';document.getElementById('pair-mode').textContent=r.capability||'--';document.getElementById('bt-state').textContent=r.bt_state||'--';document.getElementById('bt-state').className='value '+(r.bt_state=='on'?'green':'red');document.getElementById('agent-mode').textContent=r.auto_accept?'AUTO':'MANUAL';document.getElementById('agent-mode').className='value '+(r.auto_accept?'green':'yellow');var b=document.getElementById('auto-badge');b.textContent=r.auto_accept?'AUTO ACCEPT':'MANUAL';b.className='badge '+(r.auto_accept?'green':'red');document.getElementById('restart-btn').style.display=r.restart_needed?'inline-block':'none';document.getElementById('auto-on-btn').style.display=r.auto_accept?'none':'inline-block';document.getElementById('auto-off-btn').style.display=r.auto_accept?'inline-block':'none'}

async function setPin(){var v=document.getElementById('pin-input').value.trim();if(!v)return toast('Enter PIN','error');var r=await api('POST','/api/config/pin',{pin:v});if(r.error)toast(r.error,'error');else{toast('PIN = '+v);document.getElementById('restart-btn').style.display='inline-block'}}

async function setCapability(){var v=document.getElementById('cap-select').value;var r=await api('POST','/api/config/capability',{capability:v});if(r.error)toast(r.error,'error');else{toast('Mode = '+v);document.getElementById('restart-btn').style.display='inline-block'}}

async function setAutoAccept(on){var r=await api('POST','/api/agent/auto',{auto_accept:on});if(r.error)toast(r.error,'error');else toast(on?'Auto Accept ON':'Manual Confirm');loadConfig()}

async function restartService(){toast('Restarting...');var r=await api('POST','/api/restart');if(r.error)toast(r.error,'error');else setTimeout(function(){toast('Done!');loadConfig()},3000)}

// ── pairing ──
async function pollPairing(){var r=await api('GET','/api/agent/pending');if(r.error||!r.requests||!r.requests.length){setTimeout(pollPairing,1500);return}
var req=r.requests[0];
if(req.id===currentReqId){setTimeout(pollPairing,1500);return}
currentReqId=req.id;
showPopup(req);
setTimeout(pollPairing,1500)}

function showPopup(req){
var m=document.getElementById('pair-popup');
document.getElementById('popup-device').textContent='Device: '+req.device_short;
document.getElementById('popup-passkey').textContent=req.passkey||(req.kind=='pincode'?'PIN: ****':'---');
m.classList.add('show');
var end=Math.floor(req.time)+120;
function tick(){var s=Math.max(0,end-Math.floor(Date.now()/1000));document.getElementById('popup-countdown').textContent='Expires in '+s+'s';if(s>0&&m.classList.contains('show'))setTimeout(tick,1000)}
tick();
popupTimeout=setTimeout(function(){closePopup()},120000)}

function closePopup(){document.getElementById('pair-popup').classList.remove('show');currentReqId=null;if(popupTimeout)clearTimeout(popupTimeout)}

async function acceptPair(){if(!currentReqId)return;await api('POST','/api/agent/accept',{id:currentReqId});toast('Accepted!');closePopup()}

async function rejectPair(){if(!currentReqId)return;await api('POST','/api/agent/reject',{id:currentReqId});toast('Rejected','error');closePopup()}

// ── wifi ──
async function scanWifi(){var l=document.getElementById('wifi-list');l.innerHTML='<div style="color:#666">Scanning...</div>';var r=await api('POST','/api/wifi/scan');if(r.error){l.innerHTML='<div style="color:#e04040">'+r.error+'</div>';return}if(!r.networks||!r.networks.length){l.innerHTML='<div style="color:#666">None</div>';return}l.innerHTML=r.networks.map(function(n){return'<div class="network-item"><div><div class="ssid">'+(n.ssid||'(hidden)')+'</div><div class="meta">'+n.signal+' '+n.security+'</div></div><button class="btn btn-outline" onclick="qC(\''+n.ssid.replace(/'/g,"\\'")+'\')">Connect</button></div>'}).join('')}
function qC(s){document.getElementById('wifi-ssid').value=s;document.getElementById('wifi-pass').focus()}
async function connectWifi(){var s=document.getElementById('wifi-ssid').value.trim(),p=document.getElementById('wifi-pass').value;if(!s)return toast('SSID?','error');toast('Connecting...');var r=await api('POST','/api/wifi/connect',{ssid:s,password:p});if(r.success)toast('OK! IP: '+(r.ip||'?'));else toast(r.error||'Failed','error')}

// ── cmd ──
async function execCmd(){var c=document.getElementById('cmd-input').value.trim();if(!c)return toast('Command?','error');document.getElementById('cmd-output').textContent='Running...';var r=await api('POST','/api/cmd',{command:c,args:[]});document.getElementById('cmd-output').textContent=r.output||r.error||'done'}

// ── status ──
function refreshStatus(){api('GET','/api/status').then(function(r){if(!r.error){document.getElementById('wifi-state').textContent=r.wifi||'--';document.getElementById('wifi-state').className='value '+(r.wifi=='connected'?'green':'yellow')}})}
loadConfig();refreshStatus();pollPairing();setInterval(refreshStatus,5000);setInterval(loadConfig,10000);
</script>
</body>
</html>"""


class RequestHandler(BaseHTTPRequestHandler):

    server_ref = {}

    def log_message(self, fmt, *args):
        pass

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n).decode()) if n else {}

    def _srv(self):
        return self.server_ref.get("server")

    def _agent(self):
        srv = self._srv()
        return srv._agent if srv else None

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            b = INDEX_HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        elif self.path == "/api/config":
            srv = self._srv()
            agent = self._agent()
            self._json({
                "pin_code": self.server_ref.get("pin", "1234"),
                "capability": self.server_ref.get("capability", "DisplayOnly"),
                "bt_state": "on" if (srv and srv._running) else "off",
                "restart_needed": self.server_ref.get("restart_needed", False),
                "device_name": self.server_ref.get("device_name", "Bluetools"),
                "spp_channel": self.server_ref.get("spp_channel", 1),
                "auto_accept": agent._auto_accept if agent else True,
            })

        elif self.path == "/api/status":
            srv = self._srv()
            try:
                w = srv.wifi.status() if srv else {}
                self._json({"wifi": w.get("state", "unknown")})
            except Exception as e:
                self._json({"error": str(e)}, 500)

        elif self.path == "/api/agent/pending":
            agent = self._agent()
            if not agent:
                self._json({"requests": []})
                return
            pending = agent.get_pending()
            self._json({"requests": pending})

        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        try:
            d = self._read()
        except Exception:
            d = {}

        srv = self._srv()
        agent = self._agent()

        if self.path == "/api/config/pin":
            pin = str(d.get("pin", "")).strip()
            if not pin or len(pin) > 16:
                self._json({"error": "invalid"}, 400)
                return
            self.server_ref["pin"] = pin
            self.server_ref["restart_needed"] = True
            self._json({"success": True})

        elif self.path == "/api/config/capability":
            cap = d.get("capability", "")
            valid = {"NoInputNoOutput", "DisplayOnly", "KeyboardDisplay", "KeyboardOnly", "DisplayYesNo"}
            if cap not in valid:
                self._json({"error": f"Invalid"}, 400)
                return
            self.server_ref["capability"] = cap
            self.server_ref["restart_needed"] = True
            self._json({"success": True})

        elif self.path == "/api/agent/auto":
            auto = d.get("auto_accept", False)
            if agent:
                agent.set_auto_accept(auto)
            self._json({"success": True, "auto_accept": auto})

        elif self.path == "/api/agent/accept":
            rid = d.get("id")
            if agent and agent.accept(rid):
                self._json({"success": True})
            else:
                self._json({"error": "not found"}, 404)

        elif self.path == "/api/agent/reject":
            rid = d.get("id")
            if agent and agent.reject(rid):
                self._json({"success": True})
            else:
                self._json({"error": "not found"}, 404)

        elif self.path == "/api/restart":
            threading.Thread(target=_do_restart, args=(srv, self.server_ref), daemon=True).start()
            self._json({"success": True})

        elif self.path == "/api/wifi/scan":
            if not srv: self._json({"error": "no server"}, 500); return
            try:
                self._json(srv.wifi.scan())
            except Exception as e:
                self._json({"error": str(e)}, 500)

        elif self.path == "/api/wifi/connect":
            ssid = d.get("ssid", "")
            pw = d.get("password", "")
            if not ssid: self._json({"error": "no ssid"}, 400); return
            try:
                self._json(srv.wifi.connect(ssid, pw))
            except Exception as e:
                self._json({"error": str(e)}, 500)

        elif self.path == "/api/cmd":
            cmd = d.get("command", "")
            args = d.get("args", [])
            dang = d.get("dangerous", False)
            if dang or (srv and cmd in srv.system._dangerous):
                r = srv.system.execute_dangerous(cmd) if srv else {"error": "no server"}
            else:
                r = srv.system.execute(cmd, args) if srv else {"error": "no server"}
            self._json(r)

        else:
            self._json({"error": "not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


class WebServer:

    def __init__(self, server_ref, port=5000):
        self.server_ref = server_ref
        self.port = port
        self._httpd = None

    def start(self):
        RequestHandler.server_ref = self.server_ref
        self._httpd = HTTPServer(("0.0.0.0", self.port), RequestHandler)
        logger.info(f"Web UI: http://0.0.0.0:{self.port}")
        self._httpd.serve_forever()

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()


def _do_restart(srv, server_ref):
    logger.info("Restarting Bluetooth services...")
    if srv:
        if srv.ble:
            try: srv.ble.stop_advertising(); srv.ble.unregister()
            except Exception as e: logger.warning(f"CLEANUP BLE: {e}")
        if srv.spp:
            try: srv.spp.unregister()
            except Exception as e: logger.warning(f"CLEANUP SPP: {e}")
        if srv._agent:
            try: srv._agent.unregister()
            except Exception as e: logger.warning(f"CLEANUP AGENT: {e}")
    time.sleep(1)
    if srv:
        srv._set_controller_io_cap()
        srv._register_agent()
        srv._init_bluetooth_adapter()
        srv.ble.register()
        srv.ble.start_advertising()
        srv.spp.register()
    server_ref["restart_needed"] = False
    logger.info("Bluetooth restarted")
