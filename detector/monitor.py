from config import CONFIG
import os
import time
import threading
from datetime import datetime
import json
from baseline import record_request, tick_second
from detector import process_log_entry

LOG_PATH = CONFIG["log"]["path"]

_ticker_started = False


def parse_line(line: str) -> dict:
    """Convert JSON nginx log line to detector event dict.

    Args:
        line (str): _description_

    Returns:
        dict: _description_
    """
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None

    required_fields = [
        "source_ip",
        "timestamp",
        "method",
        "path",
        "status",
        "response_size",
    ]
    if not all(field in payload for field in required_fields):
        return None

    try:
        ts = str(payload["timestamp"]).replace("Z", "+00:00")
        return {
            "ip": str(payload["source_ip"]),
            "timestamp": datetime.fromisoformat(ts),
            "method": str(payload["method"]),
            "endpoint": str(payload["path"]),
            "status": int(payload["status"]),
            "size": int(payload["response_size"]),
        }
    except (TypeError, ValueError):
        return None


def tail_log(path):
    """Generator to read log file in real-time

    Args:
        path (_type_): _description_

    Yields:
        _type_: _description_
    """
    with open(path, "r") as f:
        f.seek(0, os.SEEK_END)  # Move to end of file
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.1)  # Sleep briefly if no new line
                continue
            yield line.strip()


def process_logs():
    """Main loop to process logs and detect anomalies"""
    for line in tail_log(LOG_PATH):
        data = parse_line(line)
        if not data:
            continue
        record_request(data["status"])
        process_log_entry(data)


def _baseline_tick_loop():
    """Advance baseline time series once per second."""
    while True:
        tick_second()
        time.sleep(1)


def start_monitoring(_config=None):
    """Entry point to start monitoring logs"""
    global _ticker_started
    print("Starting log monitoring...")
    if not _ticker_started:
        ticker_thread = threading.Thread(target=_baseline_tick_loop, daemon=True)
        ticker_thread.start()
        _ticker_started = True
    try:
        process_logs()
    except KeyboardInterrupt:
        print("[MONITOR] Stopped manually")
    except Exception as e:
        print(f"[MONITOR ERROR] {e}")
        time.sleep(2)
        start_monitoring(_config)
