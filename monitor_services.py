#!/usr/bin/env python3
"""
RelayPost Service Monitor
=========================
Runs on the AWS EC2 host (outside Docker containers).
Performs a two-step health check every 30 seconds.
If a service fails both checks, it restarts the Docker container automatically.

Usage:
  python3 monitor_services.py

To run as a background daemon:
  nohup python3 /usr/local/bin/monitor_services.py > /var/log/relaypost-monitor.log 2>&1 &

To run as a systemd service, see: /etc/systemd/system/relaypost-monitor.service
"""

import urllib.request
import subprocess
import time
import sys
import os
from datetime import datetime

# ─── Configuration ────────────────────────────────────────────────────────────

SERVICES = {
    "news_service": {
        "health_url": "http://localhost:8002/health",
        "container":  "news_service",
    },
    "news_generation_service": {
        "health_url": "http://localhost:8004/health",
        "container":  "news_generation_service",
    },
}

CHECK_INTERVAL_SECONDS = 30   # time between health check cycles
CONFIRM_WAIT_SECONDS   = 8    # wait before second confirmation check
HTTP_TIMEOUT_SECONDS   = 5    # socket timeout per health check request

# ─── Helpers ──────────────────────────────────────────────────────────────────

def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log(level: str, message: str):
    print(f"[{ts()}] [{level}] {message}", flush=True)

def check_health(url: str) -> bool:
    """Returns True if the URL returns HTTP 200, False for any error/timeout."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RelayPost-Monitor/1.0"})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            return resp.status == 200
    except Exception as exc:
        log("WARN", f"Health check FAILED for {url}: {exc}")
        return False

def restart_container(name: str):
    """Issue `docker restart <name>` and log the outcome."""
    log("ALERT", f"Restarting container '{name}'...")
    try:
        result = subprocess.run(
            ["docker", "restart", name],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            log("INFO", f"Container '{name}' restarted successfully.")
        else:
            log("ERROR", f"docker restart '{name}' failed: {result.stderr.strip()}")
    except FileNotFoundError:
        log("ERROR", "docker binary not found. Is Docker installed and on PATH?")
    except Exception as exc:
        log("ERROR", f"Exception while restarting '{name}': {exc}")

# ─── Main loop ────────────────────────────────────────────────────────────────

def main():
    log("INFO", f"RelayPost Monitor started. Checking every {CHECK_INTERVAL_SECONDS}s.")
    log("INFO", f"Monitoring: {list(SERVICES.keys())}")

    while True:
        for service_name, cfg in SERVICES.items():
            # ── First check ────────────────────────────────────────────────
            if check_health(cfg["health_url"]):
                log("OK", f"{service_name} is healthy.")
                continue

            # ── First check failed — wait and confirm ──────────────────────
            log("WARN", f"{service_name} failed first check. Re-checking in {CONFIRM_WAIT_SECONDS}s...")
            time.sleep(CONFIRM_WAIT_SECONDS)

            if check_health(cfg["health_url"]):
                log("INFO", f"{service_name} recovered on confirmation check (transient blip).")
                continue

            # ── Both checks failed — restart ───────────────────────────────
            log("ALERT", f"{service_name} FAILED confirmation check. Triggering restart.")
            restart_container(cfg["container"])

        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("INFO", "Monitor stopped by user (KeyboardInterrupt).")
        sys.exit(0)
    except Exception as exc:
        log("FATAL", f"Unhandled exception in monitor: {exc}")
        sys.exit(1)
