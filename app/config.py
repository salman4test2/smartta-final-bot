from __future__ import annotations
import os, yaml, threading
from typing import Any, Dict

_CONFIG = None
_LOCK = threading.Lock()

def _load():
    path = os.getenv("CONFIG_PATH", "./config/whatsapp.yaml")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}  # Graceful fallback if config missing
    except yaml.YAMLError as e:
        print(f"Warning: Invalid YAML in {path}: {e}")
        data = {}
    
    # sane defaults (align with your YAML)
    data.setdefault("model", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    data.setdefault("temperature", float(os.getenv("LLM_TEMPERATURE", "0.2")))
    data.setdefault("history", {"mode": "all", "max_turns": 200, "log_llm_io": True})
    return data

def get_config(force: bool = False) -> Dict[str, Any]:
    global _CONFIG
    with _LOCK:
        if force or _CONFIG is None:
            _CONFIG = _load()
        return _CONFIG

def reload_config() -> Dict[str, Any]:
    return get_config(force=True)

def get_cors_origins() -> list[str]:
    """Get CORS origins based on environment"""
    env = os.getenv("ENVIRONMENT", "development").lower()
    
    if env == "production":
        # Production: Use specific allowed origins
        origins = os.getenv("CORS_ORIGINS", "").split(",")
        return [origin.strip() for origin in origins if origin.strip()]
    elif env == "staging":
        # Staging: More restrictive than dev but allow staging domains
        return [
            "http://localhost:3000",
            "http://localhost:8080", 
            "https://staging-domain.com"  # Replace with actual staging domain
        ]
    else:
        # Development: Allow all origins for ease of development
        return ["*"]

def is_production() -> bool:
    """Check if running in production environment"""
    return os.getenv("ENVIRONMENT", "development").lower() == "production"
