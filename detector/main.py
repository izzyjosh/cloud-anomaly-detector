import threading
from monitor import start_monitoring
from unbanner import start_unban_scheduler
from dashboard import start_dashboard

if __name__ == "__main__":
    unban_thread = threading.Thread(target=start_unban_scheduler, daemon=True)
    unban_thread.start()

    monitor_thread = threading.Thread(target=start_monitoring, daemon=True)
    monitor_thread.start()

    start_dashboard()
