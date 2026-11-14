# launcher_bridge_probe.py
"""
Hardware-free stand-in for the engine process, used by scripts/launcher_selftest.ps1.

It exercises exactly the part of the engine the launcher depends on, without a
camera, a tracker, native input or the Tk overlay:

  * starts the real ControlServer (bridge) on the requested port,
  * writes backend/bridge_info.json and backend/.bridge_token the way main.py does
    (os.getpid() of THIS process, which under the virtual-environment launcher is
    a child of the process Start-Process returned),
  * registers the graceful-exit callback, so POST /api/control {"action": "exit"}
    ends the loop like it does in main.py,
  * publishes one Dyne event so the bridge ring is not empty,
  * stops the bridge (which removes the discovery files) on exit.

Usage:
    python launcher_bridge_probe.py [--port 8765] [--max-seconds 120]

Never run it while a real engine owns the bridge files (the self-test checks).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("airpoint.launcher_probe")


def main() -> int:
    parser = argparse.ArgumentParser(description="AirPoint launcher bridge probe (no camera, no input)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--max-seconds", type=float, default=120.0, help="exit by itself after this long")
    args = parser.parse_args()

    from core.control_server import ControlServer

    server = ControlServer(host="127.0.0.1", port=args.port)
    exit_requested = {"flag": False}

    def request_exit() -> bool:
        exit_requested["flag"] = True
        logger.info("Graceful exit requested via the control bridge (probe)")
        return True

    server.state.set_exit_cb(request_exit)
    server.start()
    server.state.publish_event("engine.started", f"Launcher probe running (pid {os.getpid()})", metadata={"probe": True})
    logger.info("Probe bridge bound to http://%s:%d (pid %d, parent %d)", server.host, server.port, os.getpid(), os.getppid())

    deadline = time.perf_counter() + max(1.0, args.max_seconds)
    try:
        while not exit_requested["flag"] and time.perf_counter() < deadline:
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        server.state.publish_event("engine.stopping", "Launcher probe stopping")
        server.stop()
        logger.info("Probe stopped (exit requested=%s)", exit_requested["flag"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
