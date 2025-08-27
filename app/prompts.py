from __future__ import annotations
import json
from typing import Dict, Any, List

def build_system_prompt(cfg: Dict[str, Any]) -> str:
    categories = cfg.get("categories") or ["MARKETING", "UTILITY", "AUTHENTICATION"]
    components = cfg.get("components") or {}
    button_kinds = (components.get("BUTTONS", {}) or {}).get("kinds", ["QUICK_REPLY", "URL", "PHONE_NUMBER"])

    schema_brief = json.dumps({
        "required": ["name", "language", "category", "components"],
        "component_types": ["HEADER", "BODY", "FOOTER", "BUTTONS"],
        "button_types": button_kinds,
        "body_required": True
    }, ensure_ascii=False)

    # Optional few-shots from config
    fews: List[str] = []
    for ex in (cfg.get("few_shots") or [])[:4]:
        u = (ex.get("user") or "").strip()
        a = json.dumps(ex.get("assistant") or {}, ensure_ascii=False)
        if u and a:
            fews.append("USER: " + u + "\nASSISTANT: " + a)
    fewshot_block = ("\n\nFEW-SHOTS (strict JSON assistant messages):\n" + "\n---\n".join(fews)) if fews else ""

    parts: List[str] = []
    parts += [
        "You are a senior assistant for building WhatsApp Business message templates.",
        "You must guide the user to a valid template creation payload with minimal back-and-forth.",
        "",
        "PRIME DIRECTIVES:",
        "1) ALWAYS return a single valid JSON object (no code fences, no extra text).",
        "2) Infer intent when obvious. Ask one concise question only if ambiguity blocks progress.",
        "3) Never re-ask facts already known (see memory + draft in the context message).",
        "4) Be multilingual: mirror user's language unless they request a specific language code.",
        "5) If the user delegates (e.g., “you choose the body/name”), propose compliant copy + snake_case name.",
        "6) Keep content brand-safe and specific; no invented private data; keep offers generic if details are missing.",
        "",
        "CATEGORY INFERENCE (examples, not exhaustive):",
        "- Festivals/occasions/promos/discount/sale/new collection/newsletter ⇒ MARKETING",
        "- Order/booking/shipping/delivery/invoice/payment/reminder/outage/alert ⇒ UTILITY",
        "- OTP/verification/login/2FA/passcode ⇒ AUTHENTICATION",
        "If unsure, ask one short clarifying question.",
        "",
        "HEADER POLICY:",
        "- If the user asks for a HEADER, include a HEADER component in the draft.",
        "- Prefer {\"type\":\"HEADER\",\"format\":\"TEXT\",\"text\":\"<≤60 chars, at most one {{1}}>\"} unless user explicitly requests IMAGE/VIDEO/DOCUMENT/LOCATION.",
        "- Do not finalize until requested header/footer/buttons are present.",
        "",
        "META CONSTRAINTS (summary):",
        "- Payload: {name, language, category, components[]} with exactly one BODY required.",
        "- Name: snake_case (lowercase, numbers, underscores), <=64 chars.",
        "- BODY: <=1024 chars; placeholders {{1..N}} sequential; avoid starting/ending with a placeholder; no adjacent placeholders.",
        "- HEADER (optional): TEXT/IMAGE/VIDEO/DOCUMENT/LOCATION; TEXT <=60 chars; max one placeholder.",
        "- FOOTER (optional): static, <=60 chars, no placeholders.",
        "- BUTTONS (optional): types listed below; keep labels concise. AUTHENTICATION templates must not add custom buttons/media.",
        "BUTTON TYPES: " + json.dumps(button_kinds, ensure_ascii=False),
        "CATEGORIES: " + json.dumps(categories, ensure_ascii=False),
        "",
        "CONVERSATION FLOW (LLM-first):",
        "- If user shares context (e.g., “today is Black Friday / Holi / Independence Day”): acknowledge, store memory.event_label, and offer MARKETING unless specified otherwise.",
        "- If user says “offer for shoes 20%”, infer MARKETING, propose a short BODY and a snake_case name, and ask only for truly missing required fields (e.g., language).",
        "- If buttons/header/footer are relevant for MARKETING/UTILITY and not discussed yet, offer once before FINAL. Store memory.extras_offered=true and memory.extras_choice='accepted'|'skip'.",
        "- For AUTHENTICATION, keep to OTP-only (BODY mentions code {{1}} and optional expiry {{2}}); do not add media or buttons.",
        "",
        "OUTPUT CONTRACT (must follow exactly; no extra keys):",
        "{",
        '  "agent_action": "ASK|DRAFT|UPDATE|FINAL|CHITCHAT",',
        '  "message_to_user": "string (one short paragraph, max ~2 sentences)",',
        '  "draft": {"category": "...", "name": "...", "language": "...", "components": [...]},',
        '  "missing": ["category","language","name","body"],',
        '  "final_creation_payload": null,',
        '  "memory": {',
        '    "category": "MARKETING|UTILITY|AUTHENTICATION",',
        '    "language_pref": "en_US|hi_IN|...",',
        '    "event_label": "e.g., holi|black friday|independence day|...",',
        '    "business_type": "e.g., shoes|sweets|electronics|...",',
        '    "buttons_request": {"count": 2, "types": ["QUICK_REPLY","URL","PHONE_NUMBER"]},',
        '    "extras_offered": true|false,',
        '    "extras_choice": "accepted|skip"',
        "  }",
        "}",
        "",
        "STRICT RULES:",
        "- Never output empty strings or empty arrays; omit unknown fields instead.",
        "- Never include code fences, markdown, or explanations outside the JSON object.",
        "- If you propose a draft BODY or name, make them reasonable and approval-friendly.",
        "- If agent_action=FINAL, ensure the draft is complete and validates against this brief: " + schema_brief + ".",
        "- If validation would fail or something is unclear, do not FINAL; ask one short question and set agent_action=ASK or DRAFT.",
        "- If the user goes off-topic (joke/weather), answer briefly (one line), store useful facts in memory if any, then steer back with a single question.",
    ]

    if fewshot_block:
        parts.append(fewshot_block)

    return "\n".join(parts)

def build_context_block(draft: Dict[str, Any], memory: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    draft = draft or {}
    memory = memory or {}

    # --- facts ---
    has_category = bool(draft.get("category") or memory.get("category"))
    has_language = bool(draft.get("language") or memory.get("language_pref"))
    has_name = bool(draft.get("name"))
    has_body = any(
        isinstance(c, dict) and c.get("type") == "BODY" and (c.get("text") or "").strip()
        for c in (draft.get("components") or [])
    )

    missing: List[str] = []
    if not has_category: missing.append("category")
    if not has_language: missing.append("language")
    if not has_body:     missing.append("body")
    if not has_name:     missing.append("name")

    # --- next action hint (LLM-first, one question max) ---
    if not has_category:
        next_step = "Ask the user for template category or infer if obvious (MARKETING/UTILITY/AUTHENTICATION)."
    elif not has_language:
        next_step = "Ask for language code (e.g., en_US, hi_IN) or infer from user language."
    elif not has_body:
        next_step = "Ask for BODY text; if the user delegated ('you choose'), propose a concise, compliant BODY."
    elif not has_name:
        next_step = "Ask for a snake_case name or propose one."
    else:
        next_step = "Offer optional HEADER/FOOTER/BUTTONS once (if MARKETING/UTILITY) before finalize; then ask to confirm FINAL."

    # --- policy + limits (read from config if available) ---
    limits_cfg = (cfg.get("limits") or {}).get("buttons", {}) or {}
    limits_note = {
        "max_total": limits_cfg.get("max_total", 10),
        "max_visible": limits_cfg.get("max_visible", 3),
        "max_url": limits_cfg.get("max_url", 2),
        "max_phone": limits_cfg.get("max_phone", 1),
        "auth_buttons": "AUTHENTICATION templates must NOT add custom buttons or media."
    }

    policy = {
        "schema_required": ["name", "language", "category", "components (BODY required)"],
        "lengths": {"body_max": 1024, "header_text_max": 60, "footer_max": 60},
        "placeholders": "Use {{1..N}} sequentially; avoid at start/end and adjacency.",
        "buttons": limits_note
    }

    # --- extras offer gate (MARKETING/UTILITY only, offer once) ---
    cat = (draft.get("category") or memory.get("category") or "").upper()
    extras_offered = bool(memory.get("extras_offered"))
    offer_extras_now = bool(cat in {"MARKETING", "UTILITY"} and has_body and not extras_offered)

    # --- shrink large JSON blobs to save tokens ---
    def _shrink(obj: Any, limit: int = 1400) -> str:
        s = json.dumps(obj, ensure_ascii=False)
        return (s[:limit] + "…") if len(s) > limit else s

    state = {
        "has_category": has_category,
        "has_language": has_language,
        "has_name": has_name,
        "has_body": has_body,
        "missing": missing,
        "offer_extras_now": offer_extras_now
    }

    return (
        "STATE:" + json.dumps(state) + "\n"
        "NEXT_STEP:" + next_step + "\n"
        "POLICY_HINTS:" + json.dumps(policy) + "\n"
        "DRAFT:" + _shrink(draft) + "\n"
        "MEMORY:" + _shrink(memory)
    )