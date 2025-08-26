# app/validator.py
from __future__ import annotations
from typing import Dict, Any, List
import re

try:
    import jsonschema
except Exception:
    jsonschema = None

def validate_schema(payload: Dict[str, Any], schema: Dict[str, Any]) -> List[str]:
    if not jsonschema:
        return ["Server missing 'jsonschema'; cannot validate creation payload."]
    try:
        v = jsonschema.Draft7Validator(schema)
        return [e.message for e in v.iter_errors(payload)]
    except Exception as e:
        return [f"Invalid JSON Schema: {e}"]

def _iter_components(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [c for c in (payload.get("components") or []) if isinstance(c, dict)]

def lint_rules(payload: Dict[str, Any], rules: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    comps = _iter_components(payload)

    # BODY required & placeholder checks
    bodies = [c for c in comps if c.get("type") == "BODY"]
    if not bodies:
        issues.append("Missing BODY component")
    else:
        body = bodies[0].get("text","")
        if len(body) > 1024: issues.append("BODY exceeds 1024 chars")
        # placeholder rules (sequential, not at start/end, not adjacent)
        ph = re.findall(r"\{\{(\d+)\}\}", body)
        if ph:
            nums = list(map(int, ph))
            if nums != list(range(1, len(nums)+1)):
                issues.append("Placeholders must be sequential {{1..N}}")
            if body.strip().startswith("{{") or body.strip().endswith("}}"):
                issues.append("BODY cannot start or end with a placeholder")
            if re.search(r"\}\}\s*\{\{", body):
                issues.append("Placeholders cannot be adjacent")

    # Footer limit
    for c in comps:
        if c.get("type") == "FOOTER":
            if c.get("text") and len(c["text"]) > 60:
                issues.append("FOOTER exceeds 60 chars")

    # Header text limit
    for c in comps:
        if c.get("type") == "HEADER" and c.get("format","TEXT") == "TEXT":
            if c.get("text") and len(c["text"]) > 60:
                issues.append("HEADER TEXT exceeds 60 chars")

    # Auth restrictions
    if (payload.get("category") == "AUTHENTICATION"):
        for c in comps:
            if c.get("type") in {"HEADER","FOOTER"}:
                issues.append("AUTHENTICATION templates should not include HEADER/FOOTER")
            if c.get("type") == "BUTTONS":
                issues.append("AUTHENTICATION templates cannot include custom buttons")

    # Button limits (config can override; keep default conservative)
    btn_limit = (rules.get("buttons") or {"max_total": 10, "max_url": 2, "max_phone": 1})
    btns = [c for c in comps if c.get("type") == "BUTTONS"]
    if btns:
        buttons = btns[0].get("buttons") or []
        if len(buttons) > btn_limit["max_total"]:
            issues.append(f"Too many buttons (>{btn_limit['max_total']})")
        url_ct = sum(1 for b in buttons if b.get("type") == "URL")
        phone_ct = sum(1 for b in buttons if b.get("type") == "PHONE_NUMBER")
        if url_ct > btn_limit["max_url"]:
            issues.append(f"Too many URL buttons (>{btn_limit['max_url']})")
        if phone_ct > btn_limit["max_phone"]:
            issues.append(f"Too many PHONE_NUMBER buttons (>{btn_limit['max_phone']})")
    return issues
