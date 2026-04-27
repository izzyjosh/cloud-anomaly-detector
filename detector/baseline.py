import time
from collections import deque, defaultdict
import statistics
from action_logger import log_action


# counter per second
current_second_count = 0  # 30 minutes window of request counts
current_second_errors = 0  # 30 minutes window of error counts

# request count per seconds
request_counts = deque(maxlen=1800)
error_counts = deque(maxlen=1800)

# per hour baseline data
hourly_data = defaultdict(
    lambda: {
        "count": deque(maxlen=1800),
        "errors": deque(maxlen=1800),
        "pending_count": 0,
        "pending_errors": 0,
        "last_recalc": 0,
        "cached": None,
    }
)

current_baseline = {
    "mean": 0,
    "stddev": 1,
    "error_rate": 0.01,
    "last_updated": 0,
}

BASELINE_RECALC_INTERVAL_SECONDS = 60
_seconds_since_recalc = 0


# -----------------------
# Recording Function
# -----------------------
def record_request(status_code: int):
    global current_second_count, current_second_errors
    current_second_count += 1
    if status_code >= 400:
        current_second_errors += 1

    # Stage current-second hourly counters; tick_second flushes them every second.
    hour = time.gmtime().tm_hour
    hourly_data[hour]["pending_count"] += 1
    if status_code >= 400:
        hourly_data[hour]["pending_errors"] += 1


def tick_second():
    """Call this every second to update baseline if needed"""
    global _seconds_since_recalc, current_second_count, current_second_errors

    # flush count for request and error per second
    request_counts.append(current_second_count)
    error_counts.append(current_second_errors)

    # set counter back to zero
    current_second_count = 0
    current_second_errors = 0

    # Flush one per-second sample for the current hour (including zeros).
    hour = time.gmtime().tm_hour
    hour_bucket = hourly_data[hour]
    hour_bucket["count"].append(hour_bucket["pending_count"])
    hour_bucket["errors"].append(hour_bucket["pending_errors"])
    hour_bucket["pending_count"] = 0
    hour_bucket["pending_errors"] = 0

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
    # Warm-up path: as soon as enough samples are collected, compute once immediately.
    if len(request_counts) >= 10 and current_baseline["mean"] == 0:
        return compute_baseline()

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

    # Recompute at most once per configured interval; return cached value otherwise.
    now = time.time()
    if (
        data["cached"] is not None
        and now - data["last_recalc"] < BASELINE_RECALC_INTERVAL_SECONDS
    ):
        return data["cached"]

    counts = list(data["count"])
    errors = list(data["errors"])

    if len(counts) < 900:  # Need at least 15 minutes of data for this hour to trust it
        return None

    mean = statistics.mean(counts)
    stddev = statistics.stdev(counts) if len(counts) > 1 else 1
    if stddev == 0:
        stddev = 1

    total_requests = sum(counts)
    total_errors = sum(errors)
    error_rate = total_errors / total_requests if total_requests > 0 else 0.01

    baseline = {
        "mean": mean,
        "stddev": stddev,
        "error_rate": error_rate,
    }

    data["cached"] = baseline
    data["last_recalc"] = now

    log_action(
        "BASELINE_UPDATE",
        f"hourly:{hour:02d}",
        condition="recalculated",
        rate="-",
        baseline=f"mean={mean:.2f},std={stddev:.2f},err={error_rate:.4f}",
        duration="-",
    )

    return baseline
