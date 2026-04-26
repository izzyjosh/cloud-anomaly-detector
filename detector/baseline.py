import time
from collections import deque, defaultdict
import statistics
from action_logger import log_action

# request count per seconds
request_counts = deque(maxlen=1800)
error_counts = deque(maxlen=1800)

# per hour baseline data
hourly_data = defaultdict(
    lambda: {"count": deque(maxlen=1800), "errors": deque(maxlen=1800), "ready": False}
)

current_baseline = {
    "mean": 0,
    "stddev": 1,
    "error_rate": 0.01,
    "last_updated": time.time(),
}

BASELINE_RECALC_INTERVAL_SECONDS = 60
_seconds_since_recalc = 0


# -----------------------
# Recording Function
# -----------------------
def record_request(status_code: int):
    request_counts.append(1)
    error_counts.append(1 if status_code >= 400 else 0)

    # update hourly data too
    hour = time.gmtime().tm_hour
    hourly_data[hour]["count"].append(1)
    hourly_data[hour]["errors"].append(1 if status_code >= 400 else 0)


def tick_second():
    """Call this every second to update baseline if needed"""
    global _seconds_since_recalc

    if len(request_counts) > 0:
        request_counts.append(0)  # Add a zero for the new second

    _seconds_since_recalc += 1
    if _seconds_since_recalc >= BASELINE_RECALC_INTERVAL_SECONDS:
        compute_baseline()
        _seconds_since_recalc = 0


# -----------------------
# Baseline Calculation
# -----------------------
def compute_baseline():
    """Calculate baseline statistics from recorded data"""

    global current_baseline

    if len(request_counts) < 10:
        return current_baseline  # Not enough data yet

    counts = list(request_counts)
    errors = list(error_counts)

    # mean and standard deviation
    mean = statistics.mean(counts)
    stddev = statistics.stdev(counts) if len(counts) > 1 else 1

    if stddev == 0:
        stddev = 1  # Avoid division by zero

    # error rate
    total = len(errors)
    error_rate = sum(errors) / total if total > 0 else 0.01

    current_baseline = {
        "mean": mean,
        "stddev": stddev,
        "error_rate": error_rate,
        "last_updated": time.time(),
    }

    log_action(
        "BASELINE_UPDATE",
        "global",
        condition="recalculated",
        rate="-",
        baseline=f"mean={mean:.2f},std={stddev:.2f}",
        duration="-",
    )

    return current_baseline


# ----------------------
# Baseline Accessor
# ----------------------
def get_baseline():
    """Get current baseline, recompute if older than 60 seconds"""
    global current_baseline
    if (
        time.time() - current_baseline["last_updated"]
        > BASELINE_RECALC_INTERVAL_SECONDS
    ):
        return compute_baseline()
    return current_baseline


def force_recompute_baseline():
    """Force recomputation of baseline"""
    return compute_baseline()


def get_effective_baseline():
    """Return the baseline the detector should prefer for current traffic."""
    hourly_baseline = get_hourly_baseline()
    if hourly_baseline is not None:
        return hourly_baseline
    return get_baseline()


# ---------------------
# Hourly smart baseline
# ---------------------
def get_hourly_baseline():
    """Get baseline for specific hour of day"""
    hour = time.gmtime().tm_hour
    data = hourly_data[hour]

    counts = list(data["count"])
    errors = list(data["errors"])

    if len(counts) < 50:
        return None

    mean = statistics.mean(counts)
    stddev = statistics.stdev(counts) if len(counts) > 1 else 1
    error_rate = sum(errors) / len(errors) if len(errors) > 0 else 0.01

    log_action(
        "BASELINE_UPDATE",
        f"hourly:{hour:02d}",
        condition="recalculated",
        rate="-",
        baseline=f"mean={mean:.2f},std={stddev:.2f},err={error_rate:.4f}",
        duration="-",
    )

    return {
        "mean": mean,
        "stddev": stddev,
        "error_rate": error_rate,
    }
