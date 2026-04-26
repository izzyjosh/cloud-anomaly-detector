import time
import psutil
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from detector import state
from blocker import get_banned_ips
from baseline import get_baseline
from config import CONFIG

app = FastAPI()

# Allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

START_TIME = time.time()


# -------------------------
# SYSTEM METRICS
# --------------------------
def get_system_metrics():
    return {
        "cpu": psutil.cpu_percent(interval=0.1),
        "memory": psutil.virtual_memory().percent,
    }


# -------------------------
# ROUTES
# -------------------------


@app.get("/")
def root():
    return {"message": "Anomaly Detection Dashboard API running"}


@app.get("/metrics")
def get_metrics():
    baseline = get_baseline()
    banned = get_banned_ips()
    system = get_system_metrics()

    return {
        "global_rps": state.get("global_rate", 0),
        "top_ips": [{"ip": ip, "rate": rate} for ip, rate in state.get("top_ips", [])],
        "banned_ips": [
            {"ip": ip, "duration": data["duration"], "strike": data["count"]}
            for ip, data in banned.items()
        ],
        "system": system,
        "baseline": {
            "mean": baseline.get("mean", 0),
            "stddev": baseline.get("stddev", 0),
            "error_rate": baseline.get("error_rate", 0),
        },
        "uptime": int(time.time() - START_TIME),
    }


# ------------------------
# START SERVER
# ------------------------


def start_dashboard():
    import uvicorn

    host = CONFIG["dashboard"]["host"]
    port = CONFIG["dashboard"]["port"]

    print(f"[DASHBOARD] Running on http://{host}:{port}")

    uvicorn.run(app, host=host, port=port)
