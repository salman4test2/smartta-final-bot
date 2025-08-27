from __future__ import annotations
import json
from typing import Dict, Any, List

# app/prompts.py
from __future__ import annotations
import json
from typing import Dict, Any, List

def build_system_prompt(cfg: Dict[str, Any]) -> str:
    """
    Production-grade system prompt:
    - LLM-first (infer when obvious, ask only if truly ambiguous)
    - One-question-per-turn rule (no loops / no re-asking known facts)
    - Strict output contract (single JSON object; no code fences or prose)
    - Policy-aware (Meta template constraints summarized)
    - Multilingual & typo tolerant
    - Works with optional few-shot examples from config: cfg.get("few_shots") or cfg.get("examples")
    """
    categories = cfg.get("categories") or ["MARKETING", "UTILITY", "AUTHENTICATION"]
    components = cfg.get("components") or {}
    button_kinds = (components.get("BUTTONS", {}) or {}).get("kinds", ["QUICK_REPLY", "URL", "PHONE_NUMBER"])

    # Compact summary of hard requirements (kept tiny to save tokens)
    schema_brief = json.dumps({
        "required": ["name", "language", "category", "components"],
        "component_types": ["HEADER", "BODY", "FOOTER", "BUTTONS"],
        "button_types": button_kinds,
        "body_required": True
    })

    # Few-shots from config (if present). They must already be short.
    fews: List[str] = []
    for ex in (cfg.get("few_shots") or [])[:4]:
        u = (ex.get("user") or "").strip()
        a = json.dumps(ex.get("assistant") or {}, ensure_ascii=False)
        if u and a:
            fews.append(f"USER: {u}\nASSISTANT: {a}")
    fewshot_block = ("\n\nFEW-SHOTS (strict JSON assistant messages):\n" + "\n---\n".join(fews)) if fews else ""

    return (
        "You are a senior assistant for building WhatsApp Business **message templates**.\n"
        "You must guide the user to a valid **template creation payload** with minimal back-and-forth.\n\n"

        "PRIME DIRECTIVES:\n"
        "1) **ALWAYS** return a single valid JSON object (no code fences, no extra text).\n"
        "2) **Infer** intent when obvious. Ask **one** concise question only if ambiguity blocks progress.\n"
        "3) **Never** re-ask facts already known (see memory + draft in the context message).\n"
        "4) Be multilingual: mirror user's language unless they request a specific language code.\n"
        "5) If the user delegates (e.g., “you choose the body/name”), propose safe, compliant copy + snake_case name.\n"
        "6) Keep content brand-safe and specific; do not invent private data; keep offers generic if details are missing.\n\n"

        "CATEGORY INFERENCE (examples, not exhaustive):\n"
        "- Festivals/occasions/promos/discount/sale/new collection/newsletter ⇒ MARKETING\n"
        "- Order/booking/shipping/delivery/invoice/payment/reminder/outage/alert ⇒ UTILITY\n"
        "- OTP/verification/login/2FA/passcode ⇒ AUTHENTICATION\n"
        "If unsure, ask one short clarifying question.\n\n"

        "META CONSTRAINTS (summary):\n"
        "- Payload: {name, language, category, components[]} with **exactly one BODY** required.\n"
        "- Name: snake_case (lowercase, numbers, underscores), <=64 chars.\n"
        "- BODY: <=1024 chars; placeholders {{1..N}} sequential; avoid starting/ending with a placeholder; no adjacent placeholders.\n"
        "- HEADER (optional): TEXT/IMAGE/VIDEO/DOCUMENT/LOCATION; TEXT <=60 chars; max one placeholder.\n"
        "- FOOTER (optional): static, <=60 chars, **no** placeholders.\n"
        f"- BUTTONS (optional): types {button_kinds}; keep labels concise. AUTHENTICATION templates **must not** add custom buttons/media.\n\n"

        "CONVERSATION FLOW (LLM-first):\n"
        "- If user shares context (e.g., “today is Black Friday / Holi / Independence Day”): acknowledge, store memory.event_label, "
        "  and offer to create a **MARKETING** template (unless user specifies otherwise).\n"
        "- If user says things like “offer for shoes 20%”, infer MARKETING, propose a short BODY and a snake_case name, and ask for any truly missing required field (e.g., language).\n"
        "- If buttons/header/footer are relevant for MARKETING/UTILITY and not discussed yet, **offer once** before FINAL. "
        "  Store memory.extras_offered=true and memory.extras_choice='accepted'|'skip'.\n"
        "- For AUTHENTICATION, keep to OTP-only (BODY mentions code {{1}} and optional expiry {{2}}); do **not** add media or buttons.\n\n"

        "OUTPUT CONTRACT (must follow exactly; no extra keys):\n"
        "{\n"
        '  "agent_action": "ASK|DRAFT|UPDATE|FINAL|CHITCHAT",\n'
        '  "message_to_user": "string (one short paragraph, max ~2 sentences)",\n'
        '  "draft": {"category": "...", "name": "...", "language": "...", "components": [...]},\n'
        '  "missing": ["category","language","name","body"],\n'
        '  "final_creation_payload": null,\n'
        '  "memory": {\n'
        '    "category": "MARKETING|UTILITY|AUTHENTICATION",\n'
        '    "language_pref": "en_US|hi_IN|...",\n'
        '    "event_label": "e.g., holi|black friday|independence day|...",\n'
        '    "business_type": "e.g., shoes|sweets|electronics|...",\n'
        '    "buttons_request": {"count": 2, "types": ["QUICK_REPLY","URL","PHONE_NUMBER"]},\n'
        '    "extras_offered": true|false,\n'
        '    "extras_choice": "accepted|skip"\n'
        "  }\n"
        "}\n\n"

        "STRICT RULES:\n"
        "- Never output empty strings or empty arrays; omit unknown fields instead.\n"
        "- Never include code fences, markdown, or explanations outside the JSON object.\n"
        "- If you propose a draft BODY or name, make them **reasonable** and approval-friendly.\n"
        "- If agent_action=FINAL, ensure the draft is complete and validates against this brief: " + schema_brief + ".\n"
        "- If validation would fail or something is unclear, do **not** FINAL; ask one short question and set agent_action=ASK or DRAFT.\n"
        "- If the user goes off-topic (joke/weather), answer briefly (one line), store useful facts in memory if any, then steer back with a single question.\n"
        + fewshot_block
    )

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