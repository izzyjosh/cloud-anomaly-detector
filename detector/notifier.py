import requests
import time
from config import load_config

# Retry settings
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


def send_alert(message: str):
    """
    Send alert to Slack
    """
    webhook_url = load_config()["slack"].get("webhook_url")

    if not webhook_url:
        print("[NOTIFIER] No webhook configured, skipping alert")
        return

    payload = {"text": message}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(webhook_url, json=payload, timeout=5)

            if response.status_code == 200:
                return
            else:
                print(f"[NOTIFIER] Slack error: {response.status_code} {response.text}")

        except requests.exceptions.RequestException as e:
            print(f"[NOTIFIER ERROR] Attempt {attempt}: {e}")

        time.sleep(RETRY_DELAY)

    print("[NOTIFIER] Failed to send alert after retries")


# -------------------------
# STRUCTURED ALERT HELPERS
# -------------------------
def alert_ip_ban(ip, rate, baseline, duration, reason):
    message = (
        f"🚨 *IP BANNED*\n"
        f"IP: `{ip}`\n"
        f"Rate: `{rate:.2f} req/s`\n"
        f"Baseline: `{baseline:.2f}`\n"
        f"Reason: `{', '.join(reason)}`\n"
        f"Duration: `{format_duration(duration)}`\n"
        f"Time: `{current_time()}`"
    )

    send_alert(message)


def alert_ip_unban(ip, duration, count):
    message = (
        f"✅ *IP UNBANNED*\n"
        f"IP: `{ip}`\n"
        f"Previous Duration: `{format_duration(duration)}`\n"
        f"Strike Count: `{count}`\n"
        f"Time: `{current_time()}`"
    )

    send_alert(message)


def alert_global_anomaly(rate, baseline):
    message = (
        f"⚠️ *GLOBAL ANOMALY*\n"
        f"Rate: `{rate:.2f} req/s`\n"
        f"Baseline: `{baseline:.2f}`\n"
        f"Time: `{current_time()}`"
    )

    send_alert(message)


# ------------------------
# UTILITIES
# ------------------------
def format_duration(seconds):
    if seconds == -1:
        return "PERMANENT"

    minutes = seconds // 60
    hours = minutes // 60

    if hours > 0:
        return f"{hours}h"
    return f"{minutes}m"


def current_time():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
