# app/prompts.py
from __future__ import annotations
import json
from typing import Dict, Any

def build_system_prompt(cfg: Dict[str, Any]) -> str:
    schema_brief = json.dumps({
        "required": ["name","language","category","components"],
        "component_types": ["HEADER","BODY","FOOTER","BUTTONS"],
        "button_types": ["QUICK_REPLY","URL","PHONE_NUMBER"]
    })
    return (
        "You are an expert WhatsApp Template Builder.\n"
        "Task: produce a *creation payload only* for Meta (no sending), or ask ONE concise question if blocked.\n"
        "Own all decisions: category (MARKETING|UTILITY|AUTHENTICATION), language, event label, name, body/header/footer, buttons.\n"
        "Maintain memory and never re-ask known facts. Return strict JSON with keys: "
        "{agent_action,message_to_user,draft,missing,final_creation_payload,memory}.\n"
        "When complete, set agent_action=FINAL and put a fully-valid creation payload into final_creation_payload.\n"
        "Validate yourself against: " + schema_brief + "\n"
        "Memory keys to fill every turn if possible: "
        "{\"category\",\"category_confidence\",\"event_label\",\"business_type\",\"language_pref\","
        "\"buttons_request\":{\"count\", \"types\"}}.\n"
        "If user mixes chitchat with intent, acknowledge and proceed.\n"
        "Never stall or loop; never output non-JSON."
    )

def build_context_block(draft: Dict[str, Any], memory: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    policy = {
        "schema_hard_requirements": ["name","language","category","components(BODY required)"],
        "button_limits_note": "WhatsApp supports up to ~10 buttons total; visible ≈3; ≤2 URL; ≤1 phone; auth=OTP only.",
        "footer_limit": "≤60 chars, static; no placeholders.",
        "header_text_limit": "≤60 chars; ≤1 placeholder.",
        "body_limit": "≤1024 chars; placeholders {{1..N}}; sequential; not at start/end; not adjacent."
    }
    return (
        "Context:\n"
        f"CurrentDraft: {json.dumps(draft, ensure_ascii=False)}\n"
        f"Memory: {json.dumps(memory or {}, ensure_ascii=False)}\n"
        f"PolicyHints: {json.dumps(policy)}\n"
        "Output contract reminder: "
        "{agent_action,message_to_user,draft,missing,final_creation_payload,memory} only."
    )
