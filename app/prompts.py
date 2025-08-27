# app/prompts.py
from __future__ import annotations
import json
from typing import Dict, Any, List

def build_system_prompt(cfg: Dict[str, Any]) -> str:
    """
    Production prompt: loop-proof, slot-driven, JSON-only.
    The model must:
      - Inspect DRAFT, MEMORY and RECENT_HISTORY from the context block
      - Derive missing fields when obvious; confirm in one sentence
      - Never re-ask already-known facts
      - Never get stuck on "yes"/"ok" loops; apply pending offers and move on
    """
    categories = cfg.get("categories") or ["MARKETING", "UTILITY", "AUTHENTICATION"]
    components = cfg.get("components") or {}
    button_kinds = (components.get("BUTTONS", {}) or {}).get("kinds", ["QUICK_REPLY", "URL", "PHONE_NUMBER"])

    schema_brief = json.dumps({
        "required": ["name", "language", "category", "components"],
        "component_types": ["HEADER", "BODY", "FOOTER", "BUTTONS"],
        "button_types": button_kinds,
        "body_required": True
    })

    return (
        "You are a production-grade WhatsApp Business template builder.\n"
        "Goal: return structured JSON that advances the template toward a valid creation payload.\n\n"

        "MUST:\n"
        "- Output a single JSON object only: {agent_action, message_to_user, draft, missing, final_creation_payload, memory}\n"
        "- Inspect the context sections: DRAFT, MEMORY, CHECKLIST and RECENT_HISTORY.\n"
        "- Use a SLOT CHECKER each turn to compute what is present vs missing per schema.\n"
        "- If a missing field can be derived from RECENT_HISTORY, propose it and ask for confirmation in one sentence.\n"
        "- Never re-ask facts already present in DRAFT/MEMORY.\n"
        "- Never stall on 'yes/ok/sure' loops; apply your last pending offer and continue.\n"
        "- Keep replies short (max ~2 sentences) and stay on task.\n\n"

        "SLOT CHECKER (every turn):\n"
        "1) Read DRAFT and MEMORY.\n"
        "2) Required slots: category, language, name, BODY.text.\n"
        "3) Build 'missing' as any required slot not present.\n"
        "4) For each missing slot, scan RECENT_HISTORY (typos allowed) to derive candidates; if you do, add them to 'draft' and mention you assumed it; ask for quick confirmation.\n"
        "5) If the user asked for HEADER/FOOTER/BUTTONS, include them (short, policy-safe). Do not wait for more turns if intent is clear.\n\n"

        "CATEGORIES (infer, not exhaustive):\n"
        "- Promos/occasions/discount/sale/new collection => MARKETING\n"
        "- Order/booking/shipping/delivery/invoice/payment/reminder/alert => UTILITY\n"
        "- OTP/verification/login/2FA => AUTHENTICATION\n"
        "If truly unclear, ask exactly one short question.\n\n"

        "LANGUAGE:\n"
        "- Mirror the user's language if none specified; otherwise use an explicit code (e.g., en_US, hi_IN).\n\n"

        "COMPONENT RULES (summary):\n"
        "- BODY required (<=1024 chars). Placeholders {{1..N}} sequential; avoid start/end and adjacency.\n"
        "- HEADER optional: TEXT/IMAGE/VIDEO/DOCUMENT/LOCATION; TEXT <=60 chars; max one placeholder.\n"
        "- FOOTER optional: static <=60 chars, no placeholders.\n"
        f"- BUTTONS optional: kinds {button_kinds}; concise labels. AUTHENTICATION must not add custom buttons/media.\n\n"

        "FINALIZATION:\n"
        "- agent_action=FINAL only when user explicitly confirms or clearly affirms AND the payload validates this brief: " + schema_brief + ".\n"
        "- Otherwise use ASK (one question) or DRAFT/UPDATE with concrete progress.\n\n"

        "OUTPUT SHAPE (strict keys, no extras):\n"
        "{\n"
        '  \"agent_action\": \"ASK|DRAFT|UPDATE|FINAL|CHITCHAT\",\n'
        '  \"message_to_user\": \"string\",\n'
        '  \"draft\": {\"category\": \"...\", \"name\": \"...\", \"language\": \"...\", \"components\": [...]},\n'
        '  \"missing\": [\"category\",\"language\",\"name\",\"body\"],\n'
        '  \"final_creation_payload\": null,\n'
        '  \"memory\": {\n'
        '    \"category\": \"MARKETING|UTILITY|AUTHENTICATION\",\n'
        '    \"language_pref\": \"en_US|hi_IN|...\",\n'
        '    \"event_label\": \"e.g., holi|black friday|independence day\",\n'
        '    \"business_type\": \"e.g., shoes|sweets|electronics\",\n'
        '    \"wants_header\": true|false,\n'
        '    \"wants_footer\": true|false,\n'
        '    \"wants_buttons\": true|false,\n'
        '    \"extras_offered\": true|false,\n'
        '    \"extras_choice\": \"accepted|skip\"\n'
        "  }\n"
        "}\n"
    )

# app/prompts.py
def build_context_block(
    draft: Dict[str, Any],
    memory: Dict[str, Any],
    cfg: Dict[str, Any],
    msgs: List[Dict[str, str]] | None = None
) -> str:
    # present state
    has_category = bool(draft.get("category") or memory.get("category"))
    has_language = bool(draft.get("language") or memory.get("language_pref"))
    has_name = bool(draft.get("name"))
    has_body = any(
        c.get("type") == "BODY" and (c.get("text") or "").strip()
        for c in (draft.get("components") or [])
    )

    checklist = {
        "required": ["category", "language", "name", "body"],
        "present": {
            "category": has_category,
            "language": has_language,
            "name": has_name,
            "body": has_body,
        },
        "missing": [
            slot for slot, ok in [
                ("category", has_category),
                ("language", has_language),
                ("name", has_name),
                ("body", has_body),
            ] if not ok
        ],
    }

    # short recent user history to allow derivation (typos and paraphrases)
    recent_user_msgs = []
    if msgs:
        for m in msgs[-8:]:
            if (m.get("role") or "") == "user":
                recent_user_msgs.append(m.get("content", "")[:300])

    policy = {
        "lengths": {"body_max": 1024, "header_text_max": 60, "footer_max": 60},
        "buttons_note": "≈3 visible; ≤2 URL; ≤1 phone; total ≤ ~10; AUTH=OTP only.",
    }

    return (
        "DRAFT: " + json.dumps(draft or {}, ensure_ascii=False) + "\n"
        "MEMORY: " + json.dumps(memory or {}, ensure_ascii=False) + "\n"
        "CHECKLIST: " + json.dumps(checklist, ensure_ascii=False) + "\n"
        "RECENT_HISTORY (user-only): " + json.dumps(recent_user_msgs, ensure_ascii=False) + "\n"
        "POLICY_HINTS: " + json.dumps(policy, ensure_ascii=False)
    )
