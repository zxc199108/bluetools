#!/system/bin/sh
# =============================================
#  Android Bluetooth SPP Client (root required)
#  Put this script on your Android device
# =============================================
#
# Usage:
#   sh btctl.sh pair          # Pair with Bluetools
#   sh btctl.sh connect       # Connect SPP channel
#   sh btctl.sh send '{"type":"ping"}'
#   sh btctl.sh wifi-scan
#   sh btctl.sh cmd uptime
#

BOARD_MAC=""      # Fill in your board's Bluetooth MAC, e.g. "AA:BB:CC:DD:EE:FF"
BOARD_NAME="Bluetools"
PIN="1234"
SPP_CHANNEL=1

die() { echo "ERROR: $*"; exit 1; }

find_mac() {
    if [ -z "$BOARD_MAC" ]; then
        echo "Scanning for $BOARD_NAME ..."
        hcitool scan | while read -r line; do
            mac=$(echo "$line" | awk '{print $1}')
            name=$(echo "$line" | cut -d' ' -f2-)
            if [ "$name" = "$BOARD_NAME" ]; then
                echo "$mac"
                return
            fi
        done
    else
        echo "$BOARD_MAC"
    fi
}

pair() {
    MAC=$(find_mac)
    [ -z "$MAC" ] && die "Device not found. Set BOARD_MAC or ensure board is discoverable"
    echo "Pairing with $MAC ..."
    bluetoothctl <<EOF
agent on
default-agent
pair $MAC
$PIN
yes
yes
quit
EOF
    echo "Paired."
}

connect_spp() {
    MAC=$(find_mac)
    [ -z "$MAC" ] && die "Device not found"
    echo "Connecting SPP to $MAC ch=$SPP_CHANNEL ..."
    rfcomm connect 0 "$MAC" $SPP_CHANNEL &
    sleep 2
    echo "Connected. /dev/rfcomm0 is ready."
}

send() {
    [ ! -e /dev/rfcomm0 ] && connect_spp
    echo "$1" > /dev/rfcomm0
    sleep 1
    cat /dev/rfcomm0 &
    sleep 1
    kill %1 2>/dev/null
}

case "${1:-}" in
    pair)    pair ;;
    connect) connect_spp ;;
    send)    send "${2:-}" ;;
    wifi-scan) send '{"type":"wifi_scan"}' ;;
    wifi-list) send '{"type":"wifi_scan"}' | python3 -c "import sys,json; d=json.load(sys.stdin); [print(n['ssid'],n['signal']) for n in d.get('networks',[])]" 2>/dev/null ;;
    wifi-connect) send "{\"type\":\"wifi_connect\",\"ssid\":\"${2}\",\"password\":\"${3:-}\"}" ;;
    ping)    send '{"type":"ping"}' ;;
    cmd)     send "{\"type\":\"cmd\",\"command\":\"${2}\",\"args\":[]}" ;;
    *)
        echo "Usage: sh btctl.sh {pair|connect|send|ping|wifi-scan|wifi-connect|cmd}"
        echo ""
        echo "First: fill BOARD_MAC or run 'pair' to find & pair"
        echo "Then:  sh btctl.sh connect     # open SPP channel"
        echo "       sh btctl.sh ping         # test"
        echo "       sh btctl.sh wifi-scan    # scan WiFi"
        echo "       sh btctl.sh cmd uptime   # run command"
        ;;
esac
