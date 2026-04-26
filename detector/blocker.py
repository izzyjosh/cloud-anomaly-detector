import time
import subprocess
from config import Config

BAN_DURATION = Config["blocker"]["ban_duration"]

banned_ips = {}


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
    except subprocess.CalledProcessError as e:
        print(f"[BLOCKER ERROR] {e}")


def _is_ip_banned(ip):
    """Check if IP is currently banned

    Args:
        ip (_type_): _description_
    Returns:
        _type_: _description_
    """
    result = subprocess.run(
        ["iptables", "-L", "INPUT", "-v", "-n"], capture_output=True, text=True
    )
    return ip in result.stdout


def ban_ip(ip):
    """Ban IP using iptables

    Args:
        ip (_type_): _description_
    """
    if _is_ip_banned(ip):
        print(f"[BLOCKER] IP {ip} is already banned")
        return

    # determin strike count
    previous = banned_ips.get(ip, {"count": 0})
    count = previous["count"] + 1

    # get ban duration based on strike count
    if count - 1 < len(BAN_DURATION):
        duration = BAN_DURATION[count - 1]
    else:
        duration = -1

    # apply iptables rule if not present
    if not _is_ip_banned(ip):
        _run_command(["iptables", "-A", "INPUT", "-s", ip, "-j", "DROP"])

    banned_ips[ip] = {"count": count, "banned_at": time.time(), "duration": duration}

    print(f"[BLOCKER] Banned {ip} for {duration} seconds (strike {count})")


# ------------------------
# Unban logic
# ------------------------
def unban_ip(ip):
    """
    Remove IP from iptables
    """
    try:
        subprocess.run(["iptables", "-D", "INPUT", "-s", ip, "-j", "DROP"], check=True)
        print(f"[BLOCKER] Unbanned {ip}")
    except subprocess.CalledProcessError:
        print(f"[BLOCKER] Failed to unban {ip}")

    if ip in banned_ips:
        del banned_ips[ip]


# -----------------
# access point
# -----------------
def get_banned_ips():
    return banned_ips
