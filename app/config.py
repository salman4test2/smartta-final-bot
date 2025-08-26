from __future__ import annotations
import os, hashlib
from pathlib import Path
from typing import Any, Dict
import yaml

_DEFAULT_CFG: Dict[str, Any] = {
    "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
    "temperature": float(os.getenv("LLM_TEMPERATURE", "0.2")),
    "history": {"mode": "all", "max_turns": 200, "log_llm_io": True},
}

CFG_PATH = os.getenv("CONFIG_PATH", "./config/whatsapp.yaml")

_cache: Dict[str, Any] = {"cfg": _DEFAULT_CFG, "cksum": ""}

def load_config() -> Dict[str, Any]:
    path = Path(CFG_PATH)
    if not path.exists():
        return _DEFAULT_CFG
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg = {**_DEFAULT_CFG, **data}
    return cfg

def checksum() -> str:
    try:
        b = Path(CFG_PATH).read_bytes()
    except Exception:
        return ""
    import hashlib as _h
    return _h.sha256(b).hexdigest()

def get_config(force: bool = False) -> Dict[str, Any]:
    cks = checksum()
    if force or cks != _cache.get("cksum"):
        _cache["cfg"] = load_config()
        _cache["cksum"] = cks
    return _cache["cfg"]
