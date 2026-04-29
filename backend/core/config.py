import os
import json

BASE_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_base_dir():
    # Return root directory e:\workspace\ddl
    return os.path.dirname(BASE_APP_DIR)

CONFIG_PATH = os.path.join(get_base_dir(), "config.json")

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            # Backward compatibility
            if isinstance(cfg.get("parse_api_key"), str):
                cfg["parse_api_key"] = [k.strip() for k in cfg["parse_api_key"].split(",") if k.strip()]
            return cfg
    return {
        "parse_api_url": "https://api.siliconflow.cn/v1",
        "parse_api_key": [],
        "parse_model": "Qwen/Qwen3-VL-235B-A22B-Thinking",
        "chat_api_url": "https://api.siliconflow.cn/v1",
        "chat_api_key": "",
        "chat_model": "Qwen/Qwen3-VL-235B-A22B-Thinking"
    }

def save_config(new_config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(new_config, f, indent=4, ensure_ascii=False)
