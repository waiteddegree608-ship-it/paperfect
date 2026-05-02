import os
from dotenv import dotenv_values, set_key

BASE_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_base_dir():
    # Return root directory e:\workspace\ddl
    return os.path.dirname(BASE_APP_DIR)

ENV_PATH = os.path.join(get_base_dir(), ".env")

def load_config():
    if not os.path.exists(ENV_PATH):
        # Create empty .env if not exists
        open(ENV_PATH, 'w').close()
        
    env_dict = dotenv_values(ENV_PATH)
    
    cfg = {
        "parse_api_url": env_dict.get("PARSE_API_URL", "https://api.siliconflow.cn/v1"),
        "parse_api_key": [],
        "parse_model": env_dict.get("PARSE_MODEL", "Qwen/Qwen2.5-72B-Instruct"),
        "chat_api_url": env_dict.get("CHAT_API_URL", "https://api.siliconflow.cn/v1"),
        "chat_api_key": env_dict.get("CHAT_API_KEY", ""),
        "chat_model": env_dict.get("CHAT_MODEL", "Qwen/Qwen2.5-72B-Instruct"),
        "paper_api_url": env_dict.get("PAPER_API_URL", ""),
        "paper_api_key": env_dict.get("PAPER_API_KEY", ""),
        "paper_model": env_dict.get("PAPER_MODEL", ""),
        "annotator_api_url": env_dict.get("ANNOTATOR_API_URL", ""),
        "annotator_api_key": env_dict.get("ANNOTATOR_API_KEY", ""),
        "annotator_model": env_dict.get("ANNOTATOR_MODEL", ""),
        "translate_api_url": env_dict.get("TRANSLATE_API_URL", ""),
        "translate_api_key": env_dict.get("TRANSLATE_API_KEY", ""),
        "translate_model": env_dict.get("TRANSLATE_MODEL", "")
    }
    
    # Process the comma-separated parse API keys list for backward compatibility with existing code
    raw_parse_keys = env_dict.get("PARSE_API_KEY", "")
    if raw_parse_keys:
        cfg["parse_api_key"] = [k.strip() for k in raw_parse_keys.split(",") if k.strip()]
        
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
