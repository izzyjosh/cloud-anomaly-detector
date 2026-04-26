import time
from blocker import banned_ips, unban_ip
from notifier import send_alert

CHECK_INTERVAL = 60  # seconds


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

    message = (
        f"✅ IP UNBANNED\n"
        f"IP: {ip}\n"
        f"Previous Duration: {data['duration']} seconds\n"
        f"Strike Count: {data['count']}"
    )

    send_alert(message)
