import time
from pathlib import Path
import psutil
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from detector import state
from blocker import get_banned_ips
from baseline import get_effective_baseline
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

HTML_CANDIDATES = [
    Path(__file__).resolve().parent / "dashboard_ui" / "index.html",
    Path(__file__).resolve().parent.parent / "dashboard_ui" / "index.html",
]


def _resolve_html_path() -> Path | None:
    for path in HTML_CANDIDATES:
        if path.exists():
            return path
    return None


def _load_dashboard_html() -> str:
    html_path = _resolve_html_path()
    if html_path is None:
        return "<h1>Dashboard UI file not found (expected dashboard_ui/index.html)</h1>"
    return html_path.read_text(encoding="utf-8")


DASHBOARD_HTML = _load_dashboard_html()


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


@app.get("/", response_class=HTMLResponse)
def root():
    return DASHBOARD_HTML


@app.get("/health")
def health():
    return {"message": "Anomaly Detection Dashboard API running"}


@app.get("/metrics")
def get_metrics():
    baseline = get_effective_baseline()
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
