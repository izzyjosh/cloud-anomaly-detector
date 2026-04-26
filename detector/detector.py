from config import CONFIG
from collections import deque, defaultdict
from baseline import get_baseline, get_hourly_baseline
from blocker import ban_ip
from notifier import send_alert, alert_global_anomaly
from action_logger import log_action

# ---------------------
# Config values
# ----------------------
Z_SCORE_THRESHOLD = CONFIG["thresholds"]["z_score"]
SPIKE_MULTIPLIER = CONFIG["thresholds"]["spike_multiplier"]
ERROR_MULTIPLIER = CONFIG["thresholds"]["error_multiplier"]
WINDOW_SIZE = CONFIG["thresholds"]["window_size"]

global_window = deque(maxlen=WINDOW_SIZE)
ip_windows = defaultdict(lambda: deque(maxlen=WINDOW_SIZE))
ip_errors_stat = defaultdict(lambda: {"total": 0, "errors": 0})

# states
state = {
    "global_rate": 0,
    "ip_rates": {},
    "top_ips": [],
}


# ----------------------
# Helper functions
# ----------------------
def clean_window(window):
    """Helper to clean window of old data

    Args:
        window (_type_): _description_

    Returns:
        _type_: _description_
    """
    while (
        len(window) > 0
        and (window[-1]["timestamp"] - window[0]["timestamp"]).total_seconds() > 60
    ):
        window.popleft()


def get_rate(window):
    """Calculate request rate for given window

    Args:
        window (_type_): _description_

    Returns:
        _type_: _description_
    """
    if len(window) == 0:
        return 0
    total_time = (window[-1]["timestamp"] - window[0]["timestamp"]).total_seconds()
    return len(window) / total_time if total_time > 0 else 0


# ----------------------
# Main entry point
# ----------------------
def process_log_entry(data):
    """Process a single log entry and update windows/statistics

    Args:
        data (_type_): _description_
    """
    global global_window, ip_windows, ip_errors_stat

    # Update global window
    global_window.append(data)
    clean_window(global_window)

    # Update IP-specific window
    ip_windows[data["ip"]].append(data)
    clean_window(ip_windows[data["ip"]])

    # Update error statistics
    ip_errors_stat[data["ip"]]["total"] += 1
    if data["status"] >= 400:
        ip_errors_stat[data["ip"]]["errors"] += 1

    # get rates and error rates
    global_rate = get_rate(global_window)
    ip_rate = get_rate(ip_windows[data["ip"]])

    # Prefer hourly baseline when enough data is available.
    baseline = get_hourly_baseline() or get_baseline()

    # baseline mean and standard deviation
    mean = baseline["mean"]
    stddev = baseline["stddev"]

    # standard score for ip adress and global
    z_score = (ip_rate - mean) / stddev if stddev > 0 else 0

    global_z = (global_rate - mean) / stddev if stddev > 0 else 0
    global_spike = global_rate > (mean * SPIKE_MULTIPLIER)

    # error rate for the IP and baseline error rate
    total = ip_errors_stat[data["ip"]]["total"]
    errors = ip_errors_stat[data["ip"]]["errors"]

    error_rate = errors / total if total > 0 else 0
    baseline_error_rate = baseline.get("error_rate", 0.01)

    error_surge = error_rate > (baseline_error_rate * ERROR_MULTIPLIER)

    # Adjust thresholds dynamically based on error surge
    effective_z_threshold = Z_SCORE_THRESHOLD
    effective_spike_multiplier = SPIKE_MULTIPLIER

    # Tighten detection sensitivity for an IP while it shows an error surge.
    if error_surge:
        effective_z_threshold = max(1.0, Z_SCORE_THRESHOLD * 0.7)
        effective_spike_multiplier = max(2.0, SPIKE_MULTIPLIER * 0.7)

    spike = ip_rate > (mean * effective_spike_multiplier)

    if z_score > effective_z_threshold or spike:
        result = []

        if z_score > effective_z_threshold:
            result.append("Z_SCORE")
        if spike:
            result.append("SPIKE")
        if error_surge:
            result.append("ERROR_SURGE")

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
