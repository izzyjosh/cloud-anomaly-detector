import time
from collection import deque, defaultdict
import statistics

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
    if len(request_counts) > 0:
        request_counts.append(0)  # Add a zero for the new second


# -----------------------
# Baseline Calculation
# -----------------------
def compute_baseline():
    """Calculate baseline statistics from recorded data"""

    global current_baseline

    if len(request_counts) < 0:
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

    return current_baseline


# ----------------------
# Baseline Accessor
# ----------------------
def get_baseline():
    """Get current baseline, recompute if older than 5 minutes"""
    global current_baseline
    if time.time() - current_baseline["last_updated"] > 300:
        return compute_baseline()
    return current_baseline


def force_recompute_baseline():
    """Force recomputation of baseline"""
    return compute_baseline()


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

    return {
        "mean": mean,
        "stddev": stddev,
        "error_rate": error_rate,
    }
