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
        "You are a helpful WhatsApp Template Builder assistant. Have natural conversations while guiding users to create valid WhatsApp message templates.\n\n"

        "🎯 YOUR MISSION:\n"
        "Help users create WhatsApp Business templates through friendly, intelligent conversation.\n"
        "Be smart about interpreting user intent, handle typos gracefully, and maintain context.\n\n"

        "🧠 INTELLIGENT INTERPRETATION:\n"
        "- 'marketing', 'merkteing', 'marketting' → MARKETING category\n"
        "- 'utility', 'utlity', 'transactional' → UTILITY category  \n"
        "- 'auth', 'authentication', 'otp', 'verification' → AUTHENTICATION category\n"
        "- Be smart about what users actually mean, not just literal text\n\n"

        "📋 CONVERSATION FLOW:\n"
        "1. If no category → Ask: 'What type of template? Marketing, Utility, or Authentication?'\n"
        "2. If category known → Ask logical next question (language, purpose, content)\n"
        "3. Build incrementally, never lose progress\n"
        "4. Handle off-topic questions briefly then redirect\n"
        "5. When ready → offer to finalize\n\n"

        "⚡ CRITICAL RULES:\n"
        "- NEVER re-ask established facts (check current draft and memory)\n"
        "- Be conversational and friendly, not robotic\n"
        "- One clear question per turn when you need info\n"
        "- Always maintain context and build upon previous responses\n"
        "- Interpret user intent intelligently (handle typos, abbreviations)\n\n"

        "🔧 TECHNICAL REQUIREMENTS:\n"
        f"Schema: {schema_brief}\n"
        "- Every template needs: category, name, language, components with BODY\n"
        "- Body text: use {{1}}, {{2}} for variables (not {1}, {2})\n"
        "- Memory keys: category, language_pref, event_label, business_type\n\n"

        "📤 OUTPUT: Always return valid JSON with these exact keys:\n"
        "{\n"
        '  "agent_action": "ASK|DRAFT|UPDATE|FINAL|CHITCHAT",\n'
        '  "message_to_user": "friendly response to user",\n'
        '  "draft": {partial or complete template},\n'
        '  "missing": ["what still needs to be collected"],\n'
        '  "final_creation_payload": null or {complete template},\n'
        '  "memory": {facts discovered so far}\n'
        "}\n\n"

        "Be helpful, intelligent, and production-ready! 🚀"
    )

def build_context_block(draft: Dict[str, Any], memory: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    # Analyze what we have vs what we need
    has_category = bool(draft.get("category") or memory.get("category"))
    has_name = bool(draft.get("name"))
    has_language = bool(draft.get("language") or memory.get("language_pref"))
    has_body = any(c.get("type") == "BODY" and c.get("text") for c in (draft.get("components") or []))

    # Determine what to ask for next
    if not has_category:
        next_step = "Ask for template category (Marketing/Utility/Authentication)"
    elif not has_language:
        next_step = "Ask for language preference"
    elif not has_body:
        next_step = "Ask what message they want to send (the main content)"
    elif not has_name:
        next_step = "Ask for template name or suggest one based on content"
    else:
        next_step = "Template is ready - offer to finalize"

    return (
        "📊 CURRENT STATUS:\n"
        f"✅ Category: {draft.get('category') or memory.get('category') or '❌ Missing'}\n"
        f"✅ Language: {draft.get('language') or memory.get('language_pref') or '❌ Missing'}\n"
        f"✅ Name: {draft.get('name') or '❌ Missing'}\n"
        f"✅ Message Content: {'✅ Has body text' if has_body else '❌ Missing'}\n\n"

        f"🎯 NEXT ACTION: {next_step}\n\n"

        f"📝 Current Draft: {json.dumps(draft, ensure_ascii=False)}\n"
        f"🧠 Memory: {json.dumps(memory or {}, ensure_ascii=False)}\n\n"

        "💡 TIPS:\n"
        "- Use {{1}}, {{2}} for placeholders in message text\n"
        "- Be conversational and build on what user already told you\n"
        "- Don't re-ask for information you already have\n"
        "- Interpret user intent smartly (handle typos and variations)"
    )
