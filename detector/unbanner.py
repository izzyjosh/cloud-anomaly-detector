import time
from blocker import unban_ip, get_banned_ips
from notifier import alert_ip_unban
from action_logger import log_action

CHECK_INTERVAL = 60  # seconds

banned_ips = get_banned_ips()


def should_unban(ip, data):
    """
    Decide if an IP should be unbanned
    """
    duration = data["duration"]

    # Permanent ban
    if duration == -1:
        return False

    elapsed = time.time() - data["banned_at"]

    return elapsed >= duration


def process_unbans():
    """
    Check all banned IPs and unban expired ones
    """
    now = time.time()
    to_unban = []

    for ip, data in list(banned_ips.items()):
        if should_unban(ip, data):
            to_unban.append(ip)

    for ip in to_unban:
        handle_unban(ip)


def handle_unban(ip):
    """
    Perform unban + notify
    """
    data = banned_ips.get(ip)

    if not data:
        return

    unban_ip(ip)
    log_action("UNBAN", ip, condition="timeout", rate="-", baseline="-", duration="-")

    alert_ip_unban(ip, data["duration"], data["count"])


def start_unban_scheduler():
    """
    Background loop
    """
    print("[UNBANNER] Started unban scheduler")

    while True:
        try:
            process_unbans()
            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            print(f"[UNBANNER ERROR] {e}")
            time.sleep(5)
