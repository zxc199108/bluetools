# Bluetools — 蓝牙远程终端

通过蓝牙 SPP 将手机变成开发板的无线终端。像 SSH 一样敲命令，不需要 WiFi。

```
手机  ── Bluetooth SPP ──►  开发板 (Ubuntu ARM64)
  │                              │
  │  $ uptime                    │  → 执行命令
  │  12:34 up 1 day              │  ← 返回输出
  │  $ df -h                     │
  │  /dev/sda  12G  3G  ...     │
```

## 安装（开发板）

```bash
cd /home/firefly/work/bluetools
sudo bash install.sh
sudo systemctl start bluetools
```

## 手机操作

**配对（一次）：** 系统蓝牙设置 → 搜到 `Bluetools` → 点配对，无需密码

**连接：** 打开 App → Devices → 选 Bluetools → Connect → 自动切到终端页

## Android App

| Tab | 功能 |
|-----|------|
| **Devices** | 扫描 / 配对 / 连接 |
| **Terminal** | 全屏终端，输入 shell 命令 |
| **WiFi** | 扫描 / 连接 WiFi |

### 编译

```bash
cd android
./gradlew assembleDebug
adb install app/build/outputs/apk/debug/app-debug.apk
```

## 终端用法

连接后在 Terminal 页直接敲命令：

```
$ uptime
  12:34:56 up 1 day,  2:30,  1 user

$ df -h
  Filesystem      Size  Used Avail Use% Mounted on
  /dev/sda2        58G   12G   43G  22% /

$ ps aux
  USER       PID %CPU %MEM    VSZ   RSS TTY
  root         1  0.0  0.1  12345  6789 ?
  ...

$ ls /home
  firefly
```

## 安全说明

当前版本**无额外鉴权**，蓝牙配对成功后即可直接执行任意 shell 命令。适用于本地开发、内网调试场景。

如需添加密码保护，改两处：

**1. 板子端** — `bluetools/simple.py`，在 `_process` 里加密码校验：

```python
REQUIRE_PASSWORD = True   # 改为 True
TERMINAL_PASSWORD = "mypass"

def _process(self, sock, addr, raw):
    # 非 JSON 走 shell 前校验密码
    try:
        m = json.loads(raw.decode())
    except:
        # 首次需先发送密码
        if raw.decode().strip() == TERMINAL_PASSWORD:
            self._authed.add(addr)
            _send(sock, {"type": "ready", "msg": "Auth OK"})
            return
        if addr not in getattr(self, '_authed', set()):
            _send(sock, {"type": "error", "error": "auth required"})
            return
        # ... 执行 shell
```

**2. 配对密码** — `bluetools/agent.py` 改 `PIN`：

```python
PIN = "你的密码"
```

> 默认 PIN `1234`，蓝牙物理范围内才能连接，适合开发调试。

## 配置

`/etc/bluetooth/main.conf`：

```ini
[General]
Name = Bluetools
DiscoverableTimeout = 0       # 始终可发现
PairableTimeout = 0            # 始终可配对
AlwaysPairable = true
```

`bluetools/simple.py` 顶部：

```python
DEVICE_NAME = "Bluetools"
SPP_CHANNEL = 1
```

## 管理命令

```bash
sudo systemctl start bluetools      # 启动
sudo systemctl stop bluetools       # 停止
sudo systemctl restart bluetools    # 重启
journalctl -u bluetools -f          # 日志
```

## 故障排查

```bash
hciconfig hci0                          # 蓝牙适配器状态
bluetoothctl show                       # 详细状态
sdptool browse local | grep "Serial"    # SPP 服务是否注册
journalctl -u bluetools -f              # 服务日志
```

**手机搜不到？** 确认 `hciconfig` 输出有 `UP RUNNING PSCAN ISCAN`。

**终端没回复？** App 点 Disconnect → Connect 重连。或检查日志是否有 `[spp] Connected`。

## 项目文件

```
bluetools/
├── install.sh                   # 安装脚本
├── main.conf                    # BlueZ 配置
├── bluetools.service            # systemd 服务
├── diag.py                      # 诊断
├── README.md
├── bluetools/
│   ├── simple.py                # 主程序 (SPP 服务器)
│   └── agent.py                 # 配对代理
└── android/                     # Android App
    └── app/src/main/java/com/bluetools/app/
        ├── MainActivity.kt      # 界面
        └── BluetoothHelper.kt   # SPP 通信
```
