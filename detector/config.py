import os
from pathlib import Path

import yaml

try:
    from dotenv import load_dotenv
except ImportError:

    def load_dotenv(*args, **kwargs):
        return False


CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")

DOTENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_config():
    load_dotenv(DOTENV_PATH)

    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)

    config["slack"]["webhook_url"] = os.getenv("WEB_HOOK_URL") or config["slack"].get(
        "webhook_url"
    )
    return config


CONFIG = load_config()
