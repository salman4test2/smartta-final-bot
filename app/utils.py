from __future__ import annotations
import hashlib
from typing import Any, Dict
import re

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

def scrub_sensitive_data(text: str) -> str:
    """
    Scrub potentially sensitive data from user input.
    Replaces emails and phone numbers with placeholder text.
    """
    if not isinstance(text, str):
        return ""
    
    # Email pattern - replace with [EMAIL]
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    text = re.sub(email_pattern, '[EMAIL]', text)
    
    # Phone number patterns - replace with [PHONE]
    # Matches various formats: +1-555-123-4567, (555) 123-4567, 555.123.4567, etc.
    phone_patterns = [
        r'\+?\d{1,3}[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',  # International and US formats
        r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',  # US format
        r'\+?\d{10,15}',  # Simple international format
    ]
    
    for pattern in phone_patterns:
        text = re.sub(pattern, '[PHONE]', text)
    
    return text
