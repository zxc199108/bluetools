"""Entry point: python3 -m bluetools

Starts Bluetooth service + Web management UI.
Web UI: http://<board-ip>:5000
"""

import sys
import logging
import argparse
import threading

from .logger import setup_logger
from .server import BluetoolsServer
from .web.server import WebServer

logger = None


def main():
    global logger

    parser = argparse.ArgumentParser(
        description="Bluetools - Bluetooth device management service"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    parser.add_argument("--port", type=int, default=5000, help="Web UI port (default: 5000)")
    parser.add_argument("--no-web", action="store_true", help="Disable web UI")
    args = parser.parse_args()

    log_level = "DEBUG" if args.verbose else "INFO"
    logger = setup_logger("bluetools", level=getattr(logging, log_level))

    server_ref = {
        "pin": "1234",
        "capability": "DisplayOnly",
        "device_name": "Bluetools",
        "spp_channel": 1,
        "restart_needed": False,
    }

    server = BluetoolsServer(server_ref=server_ref)
    server_ref["server"] = server

    if not args.no_web:
        ws = WebServer(server_ref, port=args.port)
        web_thread = threading.Thread(
            target=ws.start, daemon=True, name="webui"
        )
        web_thread.start()
        logger.info(f"Web UI: http://<board-ip>:{args.port}")

    try:
        server.start()
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=args.verbose)
        sys.exit(1)


if __name__ == "__main__":
    main()
