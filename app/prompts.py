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
        "Task: Help users create WhatsApp message templates through conversation.\n\n"
        "CRITICAL RULES:\n"
        "1. NEVER re-ask questions about facts already established (check memory/draft)\n"
        "2. If user asks unrelated questions (jokes, chitchat), acknowledge briefly then redirect to template task\n"
        "3. Always build upon existing draft - never regress or forget progress\n"
        "4. Only ask ONE focused question per turn if you need specific information\n"
        "5. Validate your own draft output - never create empty components or invalid structure\n\n"
        "CONVERSATION FLOW:\n"
        "- If category unknown → ask for category\n"
        "- If category known but missing template details → ask for specific missing info\n"
        "- Always maintain context and build incrementally\n\n"
        "OUTPUT FORMAT: Return strict JSON with keys: "
        "{agent_action,message_to_user,draft,missing,final_creation_payload,memory}\n"
        "- agent_action: ASK|DRAFT|UPDATE|FINAL|CHITCHAT\n"
        "- draft: must be valid partial/complete template (never empty components array)\n"
        "- memory: track all discovered facts\n\n"
        "SCHEMA REQUIREMENTS: " + schema_brief + "\n"
        "Memory keys to maintain: category, language_pref, event_label, business_type, buttons_request\n\n"
        "Handle chitchat gracefully but stay focused on template creation task."
    )

def build_context_block(draft: Dict[str, Any], memory: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    policy = {
        "schema_hard_requirements": ["name","language","category","components(BODY required)"],
        "button_limits_note": "WhatsApp supports up to ~10 buttons total; visible ≈3; ≤2 URL; ≤1 phone; auth=OTP only.",
        "footer_limit": "≤60 chars, static; no placeholders.",
        "header_text_limit": "≤60 chars; ≤1 placeholder.",
        "body_limit": "≤1024 chars; placeholders {{1..N}}; sequential; not at start/end; not adjacent."
    }

    # Analyze current state
    has_category = bool(draft.get("category") or memory.get("category"))
    has_name = bool(draft.get("name"))
    has_language = bool(draft.get("language") or memory.get("language_pref"))
    has_body = any(c.get("type") == "BODY" and c.get("text") for c in (draft.get("components") or []))

    state_summary = {
        "established_facts": {
            "category": has_category,
            "name": has_name, 
            "language": has_language,
            "body_content": has_body
        },
        "next_logical_step": "Ask for missing required info" if not all([has_category, has_name, has_language, has_body]) else "Ready to finalize"
    }

    return (
        "CURRENT SESSION STATE:\n"
        f"Draft: {json.dumps(draft, ensure_ascii=False)}\n"
        f"Memory: {json.dumps(memory or {}, ensure_ascii=False)}\n"
        f"Progress: {json.dumps(state_summary)}\n\n"
        f"REQUIREMENTS: {json.dumps(policy)}\n\n"
        "IMPORTANT: Build upon existing progress. Don't regress or re-ask established facts.\n"
        "OUTPUT: {agent_action,message_to_user,draft,missing,final_creation_payload,memory}"
    )
