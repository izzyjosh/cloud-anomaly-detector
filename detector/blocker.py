import time
import os
from config import CONFIG
from action_logger import log_action, format_duration
from notifier import alert_ip_ban

BAN_DURATION = CONFIG["blocker"]["ban_duration"]

# -----------------------
# Shared queue paths
# -----------------------
SHARED_DIR = "/app/shared"
BAN_FILE = os.path.join(SHARED_DIR, "ban_queue.txt")
UNBAN_FILE = os.path.join(SHARED_DIR, "unban_queue.txt")

banned_ips = {}
strike_counts = {}

WHITELIST = ["127.0.0.1", "105.117.5.163"]


# -----------------------
# Helpers
# -----------------------
def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _condition_to_reason_list(condition):
    if not condition or condition == "-":
        return ["unknown"]
    return [item.strip() for item in str(condition).split(",") if item.strip()]


def _ensure_files():
    """Ensure queue files exist"""
    os.makedirs(SHARED_DIR, exist_ok=True)
    for path in [BAN_FILE, UNBAN_FILE]:
        if not os.path.exists(path):
            open(path, "a").close()


# -----------------------
# Queue operations
# -----------------------
def queue_ban(ip, duration):
    """Write ban request to shared file"""
    _ensure_files()

    # prevent duplicate entries in same runtime
    if ip in banned_ips:
        return

    with open(BAN_FILE, "a") as f:
        f.write(f"{ip},{duration}\n")


def queue_unban(ip):
    """Write unban request to shared file"""
    _ensure_files()

    with open(UNBAN_FILE, "a") as f:
        f.write(ip + "\n")


# -----------------------
# Ban logic
# -----------------------
def ban_ip(ip, condition="-", rate="-", baseline="-"):
    """Queue IP ban (handled by host worker)"""

    if ip in WHITELIST:
        print(f"[BLOCKER] Skipping whitelist IP {ip}")
        return False

    if ip in banned_ips:
        print(f"[BLOCKER] IP {ip} already queued/banned")
        return False

    # strike tracking
    count = strike_counts.get(ip, 0) + 1
    strike_counts[ip] = count

    # duration escalation
    if count - 1 < len(BAN_DURATION):
        duration = BAN_DURATION[count - 1]
    else:
        duration = -1  # permanent

    # queue ban (NO iptables here anymore)
    queue_ban(ip, duration)

    banned_ips[ip] = {
        "count": count,
        "banned_at": time.time(),
        "duration": duration,
        "condition": condition,
        "rate": rate,
        "baseline": baseline,
    }

    duration_label = format_duration(duration)

    log_action(
        "BAN",
        ip,
        condition=condition,
        rate=rate,
        baseline=baseline,
        duration=duration_label,
    )

    alert_ip_ban(
        ip,
        _safe_float(rate),
        _safe_float(baseline),
        duration,
        _condition_to_reason_list(condition),
    )

    return True


# -----------------------
# Unban logic
# -----------------------
def unban_ip(ip):
    """Queue IP unban"""

    if ip not in banned_ips:
        return

    queue_unban(ip)
    print(f"[BLOCKER] Queued unban for {ip}")

    banned_ips.pop(ip, None)


# -----------------------
# Access
# -----------------------
def get_banned_ips():
    return banned_ips
