import yaml
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")


def load_config():
    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)

    config["slack"]["webhook_url"] = os.getenv("WEB_HOOK_URL")
    return config


CONFIG = load_config()
