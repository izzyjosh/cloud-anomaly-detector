import time


def _format_ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def format_duration(duration_seconds) -> str:
    if duration_seconds in (None, "-"):
        return "-"

    if duration_seconds == -1:
        return "permanent"

    if isinstance(duration_seconds, str):
        return duration_seconds

    minutes = int(duration_seconds) // 60
    hours = minutes // 60

    if hours > 0 and minutes % 60 == 0:
        return f"{hours}h"
    if hours > 0:
        return f"{hours}h{minutes % 60}m"
    return f"{minutes}m"


def log_action(
    action: str, ip: str, condition="-", rate="-", baseline="-", duration="-"
):
    line = f"[{_format_ts()}] {action} {ip} | {condition} | {rate} | {baseline} | {duration}"
    print(line)
