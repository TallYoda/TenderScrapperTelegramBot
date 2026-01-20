import json
import os


def load_config(path=None):
    config_path = path or os.getenv("APP_CONFIG_PATH", "config.json")
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as file:
        return json.load(file)


def get_required_config(required_keys, path=None):
    config = load_config(path)
    for key in required_keys:
        env_value = os.getenv(key)
        if env_value:
            config[key] = env_value
    missing = [key for key in required_keys if not config.get(key)]
    if missing:
        missing_list = ", ".join(missing)
        raise ValueError(f"Missing required config value(s): {missing_list}")
    return config

