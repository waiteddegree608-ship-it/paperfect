import os
from dotenv import dotenv_values, set_key

BASE_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# This is shipped as a commercial, pre-configured build: the API endpoint and
# model names are pinned by us, not the end user. The Settings UI (and the
# /api/config endpoint) must only ever let a customer supply their own API
# key(s) — never a different base URL or model name. Change these two
# constants (not the .env file) if the backend/model needs to change for a
# given release.
FIXED_API_URL = "https://opencode.ai/zen/go/v1"
FIXED_MODEL = "mimo-v2.5"

def get_base_dir():
    import sys
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    # Return root directory e:\workspace\ddl
    return os.path.dirname(BASE_APP_DIR)

ENV_PATH = os.path.join(get_base_dir(), ".env")

def load_config():
    if not os.path.exists(ENV_PATH):
        # Create empty .env if not exists
        open(ENV_PATH, 'w').close()
        
    env_dict = dotenv_values(ENV_PATH)

    def clean_key(val):
        if not val:
            return ""
        val = val.strip().strip("'").strip('"')
        if "," in val:
            parts = [p.strip().strip("'").strip('"') for p in val.split(",") if p.strip()]
            import random
            return random.choice(parts) if parts else ""
        return val
    
    # URL / model are pinned for every task type — never read from .env or
    # any user-supplied config, so a customer can only ever change the key.
    cfg = {
        "parse_api_url": FIXED_API_URL,
        "parse_api_key": [],
        "parse_model": FIXED_MODEL,
        "chat_api_url": FIXED_API_URL,
        "chat_api_key": clean_key(env_dict.get("CHAT_API_KEY", "")),
        "chat_model": FIXED_MODEL,
        "paper_api_url": FIXED_API_URL,
        "paper_api_key": clean_key(env_dict.get("PAPER_API_KEY", "")),
        "paper_model": FIXED_MODEL,
        "annotator_api_url": FIXED_API_URL,
        "annotator_api_key": clean_key(env_dict.get("ANNOTATOR_API_KEY", "")),
        "annotator_model": FIXED_MODEL,
        "translate_api_url": FIXED_API_URL,
        "translate_api_key": clean_key(env_dict.get("TRANSLATE_API_KEY", "")),
        "translate_model": FIXED_MODEL,
    }
    
    # Process the comma-separated parse API keys list for backward compatibility with existing code
    raw_parse_keys = env_dict.get("PARSE_API_KEY", "")
    if raw_parse_keys:
        raw_parse_keys = raw_parse_keys.strip().strip("'").strip('"')
        cfg["parse_api_key"] = [k.strip().strip("'").strip('"') for k in raw_parse_keys.split(",") if k.strip()]
        
    return cfg

def save_config(new_config):
    """Persist user-editable settings only. The base URL and model names are
    pinned in FIXED_API_URL / FIXED_MODEL and can never be changed from the
    UI or a raw API request — only *_API_KEY fields are ever written."""
    if not os.path.exists(ENV_PATH):
        open(ENV_PATH, 'w').close()

    for k, v in new_config.items():
        key_upper = k.upper()
        if not key_upper.endswith("_API_KEY"):
            continue
        if isinstance(v, list):
            v_str = ",".join([str(i) for i in v if i])
        else:
            v_str = str(v)
        set_key(ENV_PATH, key_upper, v_str)
