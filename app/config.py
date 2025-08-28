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
