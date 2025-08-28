# app/prompts.py
from __future__ import annotations
import json
from typing import Dict, Any, List

def build_system_prompt(cfg: Dict[str, Any]) -> str:
    """
    Production prompt: loop-proof, slot-driven, JSON-only.
    The model must:
      - Inspect DRAFT, MEMORY, CHECKLIST and RECENT_HISTORY from the context block
      - Derive missing fields when obvious; confirm in one sentence
      - Never re-ask already-known facts
      - Never get stuck on 'yes/ok' loops; apply pending offers and move on
    """
    categories = cfg.get("categories") or ["MARKETING", "UTILITY", "AUTHENTICATION"]
    components = cfg.get("components") or {}
    button_kinds = (components.get("BUTTONS", {}) or {}).get(
        "kinds", ["QUICK_REPLY", "URL", "PHONE_NUMBER"]
    )

    # compact schema brief
    schema_brief = json.dumps(
        {
            "required": ["name", "language", "category", "components"],
            "component_types": ["HEADER", "BODY", "FOOTER", "BUTTONS"],
            "button_types": button_kinds,
            "body_required": True,
        }
    )

    return (
        "You are a production-grade WhatsApp Business template builder.\n"
        "Return exactly ONE JSON object with keys: "
        "{agent_action,message_to_user,draft,missing,final_creation_payload,memory}. "
        "No code fences. No extra prose.\n\n"

        "MUST:\n"
        "- Read the context sections: DRAFT, MEMORY, CHECKLIST, RECENT_HISTORY.\n"
        "- Never re-ask already-known facts (use DRAFT/MEMORY).\n"
        "- Ask at most one short question only if something blocks progress.\n"
        "- If the user delegates content (e.g., 'you choose'), propose compliant, brand-safe text and a snake_case name.\n"
        "- Mirror user's language unless a language code is provided (en_US, hi_IN, es_MX, ...).\n"
        "- Do NOT include policy/guide keys inside draft (never put 'required', 'component_types', 'button_types', 'body_required' in draft).\n"
        "- For AUTHENTICATION: OTP-only (BODY with code {{1}}, optional expiry {{2}}). No custom buttons/media.\n\n"

        "SLOT CHECKER (run every turn):\n"
        "1) Required slots: category, language, name, BODY.text.\n"
        "2) Build 'missing' with any required slot not present.\n"
        "3) If RECENT_HISTORY lets you confidently derive a missing slot, fill it in draft and say you assumed it (ask for quick confirmation).\n"
        "4) If user asked for HEADER/FOOTER/BUTTONS, include them now with safe defaults (don't stall waiting more turns).\n\n"

        "Category inference (examples, not exhaustive): "
        "promos/occasions/discount/sale/new collection => MARKETING; "
        "order/booking/shipping/delivery/invoice/payment/reminder/alert => UTILITY; "
        "otp/verification/login/2FA => AUTHENTICATION. If truly unclear, ask one short question.\n\n"

        "Component rules (summary):\n"
        "- BODY required (<=1024 chars). Placeholders {{1..N}} sequential; avoid start/end and adjacency.\n"
        "- HEADER optional: TEXT/IMAGE/VIDEO/DOCUMENT/LOCATION; HEADER TEXT <=60 chars; max one placeholder.\n"
        "- FOOTER optional: static <=60 chars, no placeholders.\n"
        f"- BUTTONS optional: kinds {button_kinds}; concise labels. AUTHENTICATION must not add custom buttons/media.\n\n"

        "Finalization:\n"
        "- Use agent_action=FINAL when ALL required slots are filled AND user has provided content (even if indirectly). Don't wait for explicit confirmation.\n"
        "- Use agent_action=FINAL if missing=[] or only optional extras missing.\n"
        "- Set final_creation_payload to the complete template when using FINAL.\n"
        "- Brief validation: " + schema_brief + "\n\n"

        "OUTPUT (strict keys):\n"
        "{\n"
        '  "agent_action": "ASK|DRAFT|UPDATE|FINAL|CHITCHAT",\n'
        '  "message_to_user": "string (max ~2 sentences)",\n'
        '  "draft": {"category":"...","name":"...","language":"...","components":[...]},\n'
        '  "missing": ["category","language","name","body"],\n'
        '  "final_creation_payload": null (or complete template object if agent_action=FINAL),\n'
        '  "memory": {\n'
        '    "category":"MARKETING|UTILITY|AUTHENTICATION",\n'
        '    "language_pref":"en_US|hi_IN|...",\n'
        '    "event_label":"e.g., holi|black friday|independence day",\n'
        '    "business_type":"e.g., shoes|sweets|electronics",\n'
        '    "wants_header":true|false,\n'
        '    "wants_footer":true|false,\n'
        '    "wants_buttons":true|false,\n'
        '    "extras_offered":true|false,\n'
        '    "extras_choice":"accepted|skip"\n'
        "  }\n"
        "}\n"
    )


def build_context_block(
    draft: Dict[str, Any],
    memory: Dict[str, Any],
    cfg: Dict[str, Any],
    msgs: List[Dict[str, str]] | None = None,
) -> str:
    has_category = bool(draft.get("category") or memory.get("category"))
    has_language = bool(draft.get("language") or memory.get("language_pref"))
    has_name = bool(draft.get("name"))
    has_body = any(
        isinstance(c, dict) and c.get("type") == "BODY" and (c.get("text") or "").strip()
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
            slot
            for slot, ok in [
                ("category", has_category),
                ("language", has_language),
                ("name", has_name),
                ("body", has_body),
            ]
            if not ok
        ],
    }

    recent_user_msgs: List[str] = []
    if msgs:
        for m in msgs[-8:]:
            if (m.get("role") or "") == "user":
                recent_user_msgs.append((m.get("content") or "")[:300])

    policy = {
        "lengths": {"body_max": 1024, "header_text_max": 60, "footer_max": 60},
        "button_limits": (cfg.get("lint_rules") or {}).get("buttons", {}),
        "buttons_note": "≈3 visible; ≤2 URL; ≤1 phone; total ≤ ~10; AUTH=OTP only.",
    }

    return (
        "DRAFT: " + json.dumps(draft or {}, ensure_ascii=False) + "\n"
        "MEMORY: " + json.dumps(memory or {}, ensure_ascii=False) + "\n"
        "CHECKLIST: " + json.dumps(checklist, ensure_ascii=False) + "\n"
        "RECENT_HISTORY (user-only): " + json.dumps(recent_user_msgs, ensure_ascii=False) + "\n"
        "POLICY_HINTS: " + json.dumps(policy, ensure_ascii=False)
    )
