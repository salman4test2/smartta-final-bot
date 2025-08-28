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
    comps = payload.get("components") or []

    # ---- BODY presence + content ----
    body_text = None
    for c in comps:
        if isinstance(c, dict) and c.get("type") == "BODY":
            body_text = c.get("text") or ""
            break

    if not body_text or not body_text.strip():
        issues.append("Missing BODY component")
    else:
        txt = body_text
        s = txt.strip()

        # Length check
        if len(txt) > 1024:
            issues.append("BODY exceeds 1024 characters")

        # start/end placeholder (whitespace-tolerant)
        if s.startswith("{{") or s.endswith("}}"):
            issues.append("BODY cannot start or end with a placeholder")

        # adjacent placeholders ({{1}}{{2}} or with spaces)
        if re.search(r"\}\}\s*\{\{", txt):
            issues.append("Adjacent placeholders are not allowed")

        # sequential numbering {{1}}..{{N}}
        nums = [int(n) for n in re.findall(r"\{\{\s*(\d+)\s*\}\}", txt)]
        if nums and nums != list(range(1, max(nums) + 1)):
            issues.append("Placeholders must be sequential: {{1}}, {{2}}, ...")

    # ---- Language whitelist (optional) ----
    lang_rule = (rules.get("languages") or {}).get("whitelist") or []
    lang = payload.get("language")
    if lang_rule and lang and lang not in lang_rule:
        issues.append(f"Language '{lang}' not in whitelist")

    # ---- Naming policy (optional) ----
    naming = rules.get("naming") or {}
    reserved = naming.get("reserved_prefixes") or []
    name = payload.get("name") or ""
    if name and any(name.startswith(p) for p in reserved):
        issues.append(f"Name must not start with reserved prefix: {', '.join(reserved)}")

    # ---- Footer limit ----
    for c in comps:
        if isinstance(c, dict) and c.get("type") == "FOOTER":
            if c.get("text") and len(c["text"]) > 60:
                issues.append("FOOTER exceeds 60 chars")

    # ---- Header text limit ----
    for c in comps:
        if isinstance(c, dict) and c.get("type") == "HEADER" and c.get("format","TEXT") == "TEXT":
            if c.get("text") and len(c["text"]) > 60:
                issues.append("HEADER TEXT exceeds 60 chars")

    # ---- Auth restrictions ----
    if (payload.get("category") == "AUTHENTICATION"):
        for c in comps:
            if isinstance(c, dict):
                if c.get("type") in {"HEADER","FOOTER"}:
                    issues.append("AUTHENTICATION templates should not include HEADER/FOOTER")
                if c.get("type") == "BUTTONS":
                    issues.append("AUTHENTICATION templates cannot include custom buttons")

    # ---- Button limits ----
    btn_rules = rules.get("buttons") or {}
    if btn_rules:
        buttons = []
        for c in comps:
            if isinstance(c, dict) and c.get("type") == "BUTTONS":
                buttons.extend(c.get("buttons") or [])

        if buttons:
            if "max_total" in btn_rules and len(buttons) > btn_rules["max_total"]:
                issues.append(f"Too many buttons (>{btn_rules['max_total']})")

            if "max_url" in btn_rules:
                url_count = sum(1 for b in buttons if b.get("type") == "URL")
                if url_count > btn_rules["max_url"]:
                    issues.append(f"Too many URL buttons (>{btn_rules['max_url']})")

            if "max_phone" in btn_rules:
                phone_count = sum(1 for b in buttons if b.get("type") == "PHONE_NUMBER")
                if phone_count > btn_rules["max_phone"]:
                    issues.append(f"Too many PHONE_NUMBER buttons (>{btn_rules['max_phone']})")

    return issues
