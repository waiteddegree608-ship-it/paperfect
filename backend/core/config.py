"""Editable task-specific providers; old key-only installs retain their defaults."""
import os
import random
from pathlib import Path
from threading import RLock
from urllib.parse import urlsplit
from dotenv import dotenv_values, set_key

BASE_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_API_URL = "https://opencode.ai/zen/go/v1"
DEFAULT_MODEL = "mimo-v2.5"
STAGES = ("parse", "chat", "paper", "annotator", "translate", "ppt")
FIELDS = {f"{stage}_{suffix}" for stage in STAGES for suffix in ("api_url", "api_key", "model")}
_LOCK = RLock()


def get_base_dir():
    import sys
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(BASE_APP_DIR)


ENV_PATH = os.path.join(get_base_dir(), ".env")


def opencode_headers(session: str = "paperfect") -> dict:
    return {"User-Agent": "Paperfect/1.0", "x-opencode-session": (session.strip() or "paperfect")[:128]}


def load_config(*, for_settings=False):
    with _LOCK:
        values = dotenv_values(ENV_PATH) if os.path.isfile(ENV_PATH) else {}
    # Explicit .env values win so UI edits apply to new jobs. Environment
    # variables remain usable for headless/MCP installations without a .env.
    def value(name):
        return str(values.get(name.upper(), os.environ.get(name.upper(), "")) or "").strip()
    cfg = {}
    for stage in STAGES:
        cfg[f"{stage}_api_url"] = value(f"{stage}_api_url") or value("parse_api_url") or DEFAULT_API_URL
        cfg[f"{stage}_model"] = value(f"{stage}_model") or value("parse_model") or DEFAULT_MODEL
        raw = value(f"{stage}_api_key")
        if not raw and not for_settings and cfg[f"{stage}_api_url"] == (value("parse_api_url") or DEFAULT_API_URL):
            raw = value("parse_api_key")
        keys = [k.strip() for k in raw.split(",") if k.strip()]
        cfg[f"{stage}_api_key"] = keys if for_settings or stage == "parse" else (random.choice(keys) if keys else "")
    return cfg


def save_config(new_config):
    if not isinstance(new_config, dict):
        raise ValueError("Configuration must be an object")
    unknown = set(new_config) - FIELDS
    if unknown:
        raise ValueError("Unknown configuration fields: " + ", ".join(sorted(unknown)))
    validated = {}
    for key, value in new_config.items():
        if key.endswith("_api_key") and isinstance(value, list):
            if not all(isinstance(v, str) for v in value):
                raise ValueError(f"{key}: expected strings")
            value = ",".join(v.strip() for v in value if v.strip())
        if not isinstance(value, str) or any(c in value for c in "\r\n\x00"):
            raise ValueError(f"{key}: expected a single-line string")
        value = value.strip()
        if key.endswith("_api_url") and value:
            parsed = urlsplit(value)
            if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError(f"{key}: use an HTTP(S) base URL without credentials, query or fragment")
            if parsed.path.rstrip("/").endswith(("/chat/completions", "/responses")):
                raise ValueError(f"{key}: enter the base URL, usually ending in /v1")
            value = value.rstrip("/")
        validated[key.upper()] = value
    with _LOCK:
        Path(ENV_PATH).touch(exist_ok=True)
        for key, value in validated.items():
            set_key(ENV_PATH, key, value)
