import threading

from config import CONFIG
from collections import deque, defaultdict
from baseline import get_baseline, get_hourly_baseline
from blocker import ban_ip
from notifier import send_alert, alert_global_anomaly
from action_logger import log_action
import time

# ---------------------
# Config values
# ----------------------
Z_SCORE_THRESHOLD = CONFIG["thresholds"]["z_score_max"]
SPIKE_MULTIPLIER = CONFIG["thresholds"]["spike_multiplier"]
ERROR_MULTIPLIER = CONFIG["thresholds"]["error_multiplier"]
WINDOW_SIZE = CONFIG["thresholds"]["window_size"]

global_window = deque(
    maxlen=WINDOW_SIZE
)  # global request window for rate calculation: last 60 seconds
ip_windows = defaultdict(lambda: deque(maxlen=WINDOW_SIZE))

# second counter for global ip
current_second_global = {"count": 0, "errors": 0}

# second counter for ip specific
ip_current_second = defaultdict(lambda: {"count": 0, "errors": 0})

# states
state = {
    "global_rate": 0,
    "ip_rates": {},
    "top_ips": [],
}


# ----------------------
# Main entry point
# ----------------------
def process_log_entry(ip: str, status_code: int):

    # --- GLOBAL counters ---
    current_second_global["count"] += 1
    if status_code >= 400:
        current_second_global["errors"] += 1

    # --- PER-IP counters ---
    ip_current_second[ip]["count"] += 1
    if status_code >= 400:
        ip_current_second[ip]["errors"] += 1


def flush_second():
    """
    Moves per-second counters into sliding windows
    """

    # ---- GLOBAL FLUSH ----
    global_window.append(
        {
            "count": current_second_global["count"],
            "errors": current_second_global["errors"],
            "timestamp": time.time(),
        }
    )

    current_second_global["count"] = 0
    current_second_global["errors"] = 0

    # ---- PER-IP FLUSH ----
    for ip, data in ip_current_second.items():
        ip_windows[ip].append(
            {"count": data["count"], "errors": data["errors"], "timestamp": time.time()}
        )

        data["count"] = 0
        data["errors"] = 0


# -------------------------
# BACKGROUND TICKER
# -------------------------


def ticker():
    while True:
        time.sleep(1)
        flush_second()


threading.Thread(target=ticker, daemon=True).start()


# ---------------------------
# ANALYTICS FUNCTIONS
# ---------------------------


def get_global_rps():
    return sum(x["count"] for x in global_window)


def get_global_error_rate():
    total_requests = sum(x["count"] for x in global_window)
    total_errors = sum(x["errors"] for x in global_window)

    if total_requests == 0:
        return 0

    return total_errors / total_requests


def get_ip_rps(ip: str):
    return sum(x["count"] for x in ip_windows[ip])


def get_ip_error_rate(ip: str):
    window = ip_windows[ip]

    total_requests = sum(x["count"] for x in window)
    total_errors = sum(x["errors"] for x in window)

    if total_requests == 0:
        return 0

    return total_errors / total_requests


def comparism_with_baseline(data):
    global global_window, ip_windows, state

    ip = data["ip"]
    is_error = data["status"] >= 400

    # get rates and error rates
    global_rate = get_global_rps() / WINDOW_SIZE
    global_error_rate = get_global_error_rate() / WINDOW_SIZE
    ip_rate = get_ip_rps(ip)
    ip_error_rate = get_ip_error_rate(ip)

    # Prefer hourly baseline when enough data is available.
    baseline = get_hourly_baseline() or get_baseline()

    # baseline mean and standard deviation
    mean = baseline["mean"]
    stddev = baseline["stddev"]
    baseline_error_rate = baseline.get("error_rate", 0.01)

    # standard score global request
    global_z = (global_rate - mean) / stddev if stddev > 0 else 0
    global_spike = mean > 0 and (
        global_z > Z_SCORE_THRESHOLD or global_rate > (mean * SPIKE_MULTIPLIER)
    )

    # error surge for ip
    ip_error_surge = ip_error_rate > (baseline_error_rate * ERROR_MULTIPLIER)

    # Adjust thresholds dynamically based on error surge
    effective_z_threshold = Z_SCORE_THRESHOLD
    effective_spike_multiplier = SPIKE_MULTIPLIER

    # Tighten detection sensitivity for an IP while it shows an error surge.
    if ip_error_surge:
        effective_z_threshold = max(1.0, Z_SCORE_THRESHOLD * 0.7)
        effective_spike_multiplier = max(2.0, SPIKE_MULTIPLIER * 0.7)

    z_score = (ip_rate - mean) / stddev if stddev > 0 else 0
    spike = mean > 0 and ip_rate > (mean * effective_spike_multiplier)

    if z_score > effective_z_threshold or spike:
        result = []

        if z_score > effective_z_threshold:
            result.append("Z_SCORE")
        if spike:
            result.append("SPIKE")
        if ip_error_surge:
            result.append("ERROR_SURGE")

        if ip == "105.112.238.16":
            return

        handle_ip_anomaly(data["ip"], z_score, ip_rate, mean, result)

    if global_z > Z_SCORE_THRESHOLD or global_spike:
        handle_global_anomaly(global_rate, mean)

    # Update shared state
    state["global_rate"] = global_rate
    state["ip_rates"][data["ip"]] = ip_rate

    # Compute top 10 IPs
    sorted_ips = sorted(state["ip_rates"].items(), key=lambda x: x[1], reverse=True)

    state["top_ips"] = sorted_ips[:10]


# =========================
# HANDLERS
# =========================
def handle_ip_anomaly(ip, z_score, rate, baseline, reason):
    """
    Block IP + notify
    """
    condition = ",".join(reason)
    if "Z_SCORE" in reason:
        condition = f"z>{Z_SCORE_THRESHOLD}"

    ban_ip(
        ip,
        condition=condition,
        rate=f"{rate:.2f}",
        baseline=f"{baseline:.2f}",
    )

    message = (
        f"🚨 IP ANOMALY DETECTED\n"
        f"IP: {ip}\n"
        f"Rate: {rate:.2f} req/s\n"
        f"Baseline: {baseline:.2f}\n"
        f"Reason: {', '.join(reason)}\n"
        f"Action: BLOCKED"
    )

    send_alert(message)


def handle_global_anomaly(rate, baseline):
    """
    Only notify (no blocking)
    """

    alert_global_anomaly(rate, baseline)
