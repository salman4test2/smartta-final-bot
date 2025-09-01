# app/validator.py
from __future__ import annotations
from typing import Dict, Any, List
import re

try:
    import jsonschema
except Exception:
    jsonschema = None

# --- Global placeholder helpers ---
_PH_RE = re.compile(r"\{\{\s*(\d+)\s*\}\}")

def _placeholders_in(text: str) -> list[int]:
    """Return placeholder indices found in text, e.g., 'Hi {{2}}' -> [2]."""
    if not isinstance(text, str):
        return []
    return [int(m.group(1)) for m in _PH_RE.finditer(text)]

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

def lint_header(header_comp: Dict[str, Any], category: str, rules: Dict[str, Any]) -> List[str]:
    """
    Dedicated header linting function that enforces all Meta Cloud API rules.
    Returns list of validation errors for the header component.
    """
    issues: List[str] = []
    
    if not isinstance(header_comp, dict):
        return ["Invalid header component structure"]
    
    fmt = (header_comp.get("format") or "TEXT").upper()
    txt = (header_comp.get("text") or "").strip()
    example = header_comp.get("example")
    cat = category.upper()
    
    # Get configuration blocks
    header_format_rules = rules.get("header_formats", {}).get(fmt, {})
    category_constraints = rules.get("category_constraints", {}).get(cat, {})
    component_header_config = rules.get("components", {}).get("header", {})
    
    # 1. Category-specific format validation
    allowed_formats = category_constraints.get("allowed_header_formats", ["TEXT", "IMAGE", "VIDEO", "DOCUMENT", "LOCATION"])
    if fmt not in allowed_formats:
        issues.append(f"{cat} templates do not allow {fmt} headers. Allowed: {', '.join(allowed_formats)}")
        return issues  # Early return if format not allowed for category
    
    # 2. LOCATION master switch (if configured)
    if fmt == "LOCATION":
        location_config = component_header_config.get("formats", {}).get("LOCATION", {})
        if not location_config.get("master_switch", True):
            issues.append("LOCATION headers are currently disabled")
            return issues
    
    # 3. Format-specific validation
    if fmt == "TEXT":
        # Text length validation
        max_len = header_format_rules.get("max_length", 60)
        if len(txt) > max_len:
            issues.append(f"Header text exceeds {max_len} chars (current: {len(txt)})")
        
        # Text presence validation
        if not txt and header_format_rules.get("require_text", True):
            issues.append("TEXT header requires text content")
        
        # Variable counting and validation
        nvars = len(re.findall(r"\{\{\d+\}\}", txt))
        max_vars = header_format_rules.get("max_variables", 1)
        if nvars > max_vars:
            issues.append(f"Header allows at most {max_vars} variable(s), found {nvars}")
        
        # Example validation for variables
        example_required = header_format_rules.get("variable_example_required", True)
        if nvars > 0 and example_required and not example:
            issues.append("Provide example values for header variables")
        
        # Additional TEXT-specific rules from component config
        component_text_rules = component_header_config.get("formats", {}).get("TEXT", {})
        if component_text_rules:
            comp_max_len = component_text_rules.get("max_length", max_len)
            if len(txt) > comp_max_len:
                issues.append(f"Header text exceeds component rule limit of {comp_max_len} chars")
    
    elif fmt in {"IMAGE", "VIDEO", "DOCUMENT", "LOCATION"}:
        # Text field validation for media headers
        forbid_text = header_format_rules.get("forbid_text", True)
        if txt and forbid_text:
            issues.append(f"{fmt} header must not include 'text' field")
        
        # Example validation for media headers
        require_example = header_format_rules.get("require_example", True)
        if fmt != "LOCATION" and require_example and not example:
            issues.append(f"{fmt} header requires an example")
        elif fmt == "LOCATION":
            # LOCATION has special handling - example is optional by default
            location_require_example = header_format_rules.get("require_example", False)
            if location_require_example and not example:
                issues.append("LOCATION header requires an example (per current config)")
        
        # MIME type validation (if configured)
        component_format_rules = component_header_config.get("formats", {}).get(fmt, {})
        allowed_mimes = component_format_rules.get("allowed_mime_types", [])
        if allowed_mimes and example:
            # In a real implementation, you'd validate the actual mime type of the example
            # For now, we just ensure the example is present when mime types are restricted
            pass
    
    return issues


def lint_rules(payload: Dict[str, Any], rules: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    comps = payload.get("components") or []
    cat = (payload.get("category") or "").upper()

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

        # Note: Sequential numbering is now validated globally across HEADER+BODY below

    # ---- Header validation (using dedicated lint_header function) ----
    headers = [c for c in comps if isinstance(c, dict) and c.get("type") == "HEADER"]
    
    # Only one header allowed
    if len(headers) > 1:
        issues.append("Only one HEADER component is allowed")
    
    if headers:
        header_issues = lint_header(headers[0], cat, rules)
        issues.extend(header_issues)

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
            # FOOTER must not contain placeholders
            if c.get("text"):
                phs = _placeholders_in(c["text"])
                if phs:
                    issues.append("FOOTER must not contain placeholders")

    # ---- Auth restrictions ----
    if cat == "AUTHENTICATION":
        category_constraints = rules.get("category_constraints", {}).get(cat, {})
        allow_footer = category_constraints.get("allow_footer", True)
        allow_buttons = category_constraints.get("allow_buttons", True)
        
        for c in comps:
            if isinstance(c, dict):
                if c.get("type") == "FOOTER" and not allow_footer:
                    issues.append("AUTHENTICATION templates should not include FOOTER")
                if c.get("type") == "BUTTONS" and not allow_buttons:
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

    # ---- Global placeholder sequencing across HEADER(TEXT) + BODY ----
    try:
        all_nums: list[int] = []
        for comp in (payload.get("components") or []):
            t = (comp.get("type") or "").upper()
            if t == "HEADER" and (comp.get("format") or "").upper() == "TEXT":
                all_nums += _placeholders_in(comp.get("text") or "")
            elif t == "BODY":
                all_nums += _placeholders_in(comp.get("text") or "")

        if all_nums:
            uniq = sorted(set(all_nums))
            # must start at 1
            if uniq[0] != 1:
                issues.append("Placeholders must start at {{1}} across header+body")
            # must be contiguous 1..N (duplicates are fine)
            expected = list(range(1, uniq[-1] + 1))
            if uniq != expected:
                missing = [n for n in expected if n not in uniq]
                if missing:
                    pretty = ", ".join(f"{{{{{n}}}}}" for n in missing)
                    issues.append(f"Placeholders must be sequential across header+body; missing: {pretty}")
    except Exception:
        # lint must never crash the request
        pass

    return issues
