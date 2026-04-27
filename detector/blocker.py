import time
import subprocess
import os
import shutil
from config import CONFIG
from action_logger import log_action, format_duration
from notifier import alert_ip_ban

BAN_DURATION = CONFIG["blocker"]["ban_duration"]
IPTABLES_CHAIN = CONFIG["blocker"].get("iptables_chain", "DOCKER-USER")

banned_ips = {}
strike_counts = {}

IPTABLES_BIN = shutil.which("iptables")
SUDO_BIN = shutil.which("sudo")

WHITELIST = ["127.0.0.1", "105.117.5.163"]


def _needs_sudo() -> bool:
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None:
        return False
    return geteuid() != 0


def _iptables_cmd(args):
    if not IPTABLES_BIN:
        return None

    cmd = [IPTABLES_BIN, *args]
    if SUDO_BIN and _needs_sudo():
        cmd = [SUDO_BIN, *cmd]
    return cmd


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
    except FileNotFoundError as e:
        print(f"[BLOCKER ERROR] Command not found: {e}")
        return False


def _is_ip_banned(ip):
    """Check if IP is currently banned

    Args:
        ip (_type_): _description_
    Returns:
        _type_: _description_
    """
    cmd = _iptables_cmd(["-C", IPTABLES_CHAIN, "-s", ip, "-j", "DROP"])
    if not cmd:
        print("[BLOCKER ERROR] iptables is not available on this host")
        return False

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError:
        return False
    except FileNotFoundError as e:
        print(f"[BLOCKER ERROR] Could not inspect iptables rules: {e}")
        return False


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
    if ip in WHITELIST:
        print(f"[BLOCKER] Skipping whitelist IP {ip}")
        return

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
    add_cmd = _iptables_cmd(["-I", IPTABLES_CHAIN, "1", "-s", ip, "-j", "DROP"])
    if not add_cmd:
        print("[BLOCKER ERROR] iptables is not available on this host")
        return

    if not _run_command(add_cmd):
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
        del_cmd = _iptables_cmd(["-D", IPTABLES_CHAIN, "-s", ip, "-j", "DROP"])
        if not del_cmd:
            print("[BLOCKER ERROR] iptables is not available on this host")
            return

        subprocess.run(del_cmd, check=True)
        print(f"[BLOCKER] Unbanned {ip}")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"[BLOCKER] Failed to unban {ip}: {e}")
    finally:
        banned_ips.pop(ip, None)


# -----------------
# access point
# -----------------
def get_banned_ips():
    return banned_ips
