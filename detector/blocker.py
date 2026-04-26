import time
import subprocess
from config import CONFIG
from action_logger import log_action, format_duration
from notifier import alert_ip_ban

BAN_DURATION = CONFIG["blocker"]["ban_duration"]

banned_ips = {}
strike_counts = {}


# -----------------------
# Iptables helper
# -----------------------
def _run_command(cmd):
    """Helper to run shell command

    Args:
        cmd (_type_): _description_

    Returns:
        _type_: _description_
    """
    try:
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[BLOCKER ERROR] {e}")
        return False


def _is_ip_banned(ip):
    """Check if IP is currently banned

    Args:
        ip (_type_): _description_
    Returns:
        _type_: _description_
    """
    result = subprocess.run(
        ["sudo", "iptables", "-L", "INPUT", "-v", "-n"], capture_output=True, text=True
    )
    return ip in result.stdout


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _condition_to_reason_list(condition):
    if not condition or condition == "-":
        return ["unknown"]
    return [item.strip() for item in str(condition).split(",") if item.strip()]


def ban_ip(ip, condition="-", rate="-", baseline="-"):
    """Ban IP using iptables

    Args:
        ip (_type_): _description_
    """
    if _is_ip_banned(ip):
        print(f"[BLOCKER] IP {ip} is already banned")
        return

    # determine strike count across repeated bans
    count = strike_counts.get(ip, 0) + 1
    strike_counts[ip] = count

    # get ban duration based on strike count
    if count - 1 < len(BAN_DURATION):
        duration = BAN_DURATION[count - 1]
    else:
        duration = -1

    # apply iptables rule
    if not _run_command(["sudo", "iptables", "-A", "INPUT", "-s", ip, "-j", "DROP"]):
        return

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


# ------------------------
# Unban logic
# ------------------------
def unban_ip(ip):
    """
    Remove IP from iptables
    """
    try:
        subprocess.run(
            ["sudo", "iptables", "-D", "INPUT", "-s", ip, "-j", "DROP"], check=True
        )
        print(f"[BLOCKER] Unbanned {ip}")
    except subprocess.CalledProcessError:
        print(f"[BLOCKER] Failed to unban {ip}")
    finally:
        banned_ips.pop(ip, None)


# -----------------
# access point
# -----------------
def get_banned_ips():
    return banned_ips
