import threading
from monitor import start_monitoring
from unbanner import start_unban_scheduler

if __name__ == "__main__":
    unban_thread = threading.Thread(target=start_unban_scheduler, daemon=True)
    unban_thread.start()
    start_monitoring()
