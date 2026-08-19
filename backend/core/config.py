import os
from dotenv import dotenv_values, set_key

BASE_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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
    
    def clean_base_url(url_val):
        if not url_val:
            return ""
        url_val = url_val.strip().strip("'").strip('"')
        if not url_val:
            return ""
        if url_val.endswith("/"):
            url_val = url_val[:-1]
        if url_val.endswith("/messages"):
            url_val = url_val[:-9]
        elif url_val.endswith("/chat/completions"):
            url_val = url_val[:-17]
        elif url_val.endswith("/chat"):
            url_val = url_val[:-5]
        if url_val.endswith("/"):
            url_val = url_val[:-1]
        return url_val

    def clean_key(val):
        if not val:
            return ""
        val = val.strip().strip("'").strip('"')
        if "," in val:
            parts = [p.strip().strip("'").strip('"') for p in val.split(",") if p.strip()]
            import random
            return random.choice(parts) if parts else ""
        return val
    
    cfg = {
        "parse_api_url": clean_base_url(env_dict.get("PARSE_API_URL", "https://opencode.ai/zen/go/v1")),
        "parse_api_key": [],
        "parse_model": env_dict.get("PARSE_MODEL", "qwen3.7-plus").strip().strip("'").strip('"'),
        "chat_api_url": clean_base_url(env_dict.get("CHAT_API_URL", "https://opencode.ai/zen/go/v1")),
        "chat_api_key": clean_key(env_dict.get("CHAT_API_KEY", "")),
        "chat_model": env_dict.get("CHAT_MODEL", "qwen3.7-plus").strip().strip("'").strip('"'),
        "paper_api_url": clean_base_url(env_dict.get("PAPER_API_URL", "")),
        "paper_api_key": clean_key(env_dict.get("PAPER_API_KEY", "")),
        "paper_model": env_dict.get("PAPER_MODEL", "").strip().strip("'").strip('"'),
        "annotator_api_url": clean_base_url(env_dict.get("ANNOTATOR_API_URL", "")),
        "annotator_api_key": clean_key(env_dict.get("ANNOTATOR_API_KEY", "")),
        "annotator_model": env_dict.get("ANNOTATOR_MODEL", "").strip().strip("'").strip('"'),
        "translate_api_url": clean_base_url(env_dict.get("TRANSLATE_API_URL", "")),
        "translate_api_key": clean_key(env_dict.get("TRANSLATE_API_KEY", "")),
        "translate_model": env_dict.get("TRANSLATE_MODEL", "qwen3.7-plus").strip().strip("'").strip('"')
    }
    
    # Process the comma-separated parse API keys list for backward compatibility with existing code
    raw_parse_keys = env_dict.get("PARSE_API_KEY", "")
    if raw_parse_keys:
        raw_parse_keys = raw_parse_keys.strip().strip("'").strip('"')
        cfg["parse_api_key"] = [k.strip().strip("'").strip('"') for k in raw_parse_keys.split(",") if k.strip()]
        
    return cfg

def save_config(new_config):
    if not os.path.exists(ENV_PATH):
        open(ENV_PATH, 'w').close()
        
    for k, v in new_config.items():
        if isinstance(v, list):
            v_str = ",".join([str(i) for i in v if i])
        else:
            v_str = str(v)
            
        set_key(ENV_PATH, k.upper(), v_str)
