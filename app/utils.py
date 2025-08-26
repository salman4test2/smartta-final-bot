from __future__ import annotations
import hashlib
from typing import Any, Dict

def hash_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def merge_deep(a: Dict[str, Any] | None, b: Dict[str, Any] | None) -> Dict[str, Any]:
    a = dict(a or {})
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(a.get(k), dict):
            a[k] = merge_deep(a.get(k), v)
        else:
            a[k] = v
    return a
