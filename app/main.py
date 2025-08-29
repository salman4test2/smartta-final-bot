from __future__ import annotations
from typing import Dict, Any, List
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.engine.url import make_url
import os
import re
import datetime as dt

from .db import engine, SessionLocal, Base
from .models import Draft, User, UserSession
from .repo import get_or_create_session, upsert_session, create_draft, log_llm, upsert_user_session, touch_user_session
from .config import get_config, get_cors_origins, is_production
from .prompts import build_system_prompt, build_context_block
from .friendly_prompts import build_friendly_system_prompt, get_helpful_examples, get_encouragement_messages
from .llm import LlmClient
from .validator import validate_schema, lint_rules
from .schemas import ChatInput, ChatResponse, SessionData, ChatMessage
from .utils import merge_deep, scrub_sensitive_data

# Import route modules
from .routes import config, debug, users, sessions

app = FastAPI(title="LLM-First WhatsApp Template Builder", version="4.0.0")

# Include route modules
app.include_router(config.router)
app.include_router(debug.router)
app.include_router(users.router)
app.include_router(sessions.router)

import hashlib

def _qhash(s: str) -> str:
    return hashlib.sha1((s or "").encode("utf-8")).hexdigest()[:12]

def _redact_secrets(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Redact potentially sensitive information from log payloads"""
    import copy, hashlib
    if not isinstance(payload, dict):
        return payload

    redacted = copy.deepcopy(payload)

    sensitive_keys = {
        "password", "token", "api_key", "secret", "auth", "authorization",
        "cookie", "phone", "email"
    }
    hash_keys = {"user_id", "session_id"}
    preserve_keys = {"system", "context", "missing", "agent_action", "draft"}

    def _hash(s): 
        return hashlib.sha1(str(s).encode()).hexdigest()[:10]

    def walk(obj, preserve_strings=False):
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                kl = k.lower()

                # 1) hash ids for correlation
                if any(hk in kl for hk in hash_keys):
                    out[k] = f"[HASH:{_hash(v)}]"
                    continue

                # 2) redact secrets
                if any(sens in kl for sens in sensitive_keys):
                    out[k] = "[REDACTED]"
                    continue

                # 3) preserve keys (no truncation on strings)
                if k in preserve_keys:
                    # still recurse to redact nested secrets inside draft etc., but preserve strings
                    out[k] = walk(v, preserve_strings=True)
                    continue

                out[k] = walk(v, preserve_strings=False)
            return out

        if isinstance(obj, list):
            return [walk(x, preserve_strings) for x in obj]

        if isinstance(obj, str):
            if preserve_strings:
                return obj  # Don't truncate strings in preserved keys
            return obj if len(obj) <= 200 else obj[:100] + "...[TRUNCATED]"

        return obj

    return walk(redacted)

def _generate_session_name_from_message(message: str, category: str = None) -> str:
    """Generate a meaningful session name from the first user message"""
    
    # Clean the message
    clean_msg = re.sub(r'[^\w\s]', '', message.lower())
    words = clean_msg.split()
    
    # Remove common words
    stop_words = {'i', 'want', 'to', 'create', 'a', 'for', 'the', 'and', 'or', 'but', 'make', 'template', 'whatsapp'}
    meaningful_words = [w for w in words if w not in stop_words and len(w) > 2]
    
    # Take first 3-4 meaningful words
    name_words = meaningful_words[:4] if len(meaningful_words) >= 4 else meaningful_words[:3]
    
    # Add category if available
    cat = (category or '').upper()
    if cat and cat != 'UNKNOWN':
        if cat == 'MARKETING':
            name_words.append('promotion')
        elif cat == 'UTILITY':
            name_words.append('notification')
        elif cat == 'AUTHENTICATION':
            name_words.append('verification')
    
    # Create name
    if name_words:
        name = ' '.join(name_words).title()
        return f"{name} Template"
    else:
        return "New Template"

async def _auto_name_session_if_needed(db: AsyncSession, user_id: str, session_id: str, message: str, category: str = None):
    """Automatically name a session based on the first message if no name is set"""
    if not user_id:
        return
        
    from sqlalchemy import select, update
    
    # Check if session already has a name
    user_session_result = await db.execute(
        select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.session_id == session_id
        )
    )
    user_session = user_session_result.scalar_one_or_none()
    
    if user_session and not user_session.session_name:
        # Generate name from message
        auto_name = _generate_session_name_from_message(message, category)
        
        # Update session name
        await db.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.session_id == session_id)
            .values(session_name=auto_name)
        )

# --- CORS configuration based on environment ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

async def get_db() -> AsyncSession:
    async with SessionLocal() as s:
        yield s

# ---------- Startup ----------
@app.on_event("startup")
async def on_startup():
    try:
        safe = make_url(os.getenv("DATABASE_URL", "")).set(password="***")
        print(f"[DEBUG] FastAPI startup: DATABASE_URL={safe}")
    except Exception:
        pass

    # create tables
    async with engine.begin() as aconn:
        await aconn.run_sync(Base.metadata.create_all)

    # apply SQLite PRAGMAs (no-op on Postgres)
    try:
        if engine.url.drivername.startswith("sqlite"):
            # Warn if using SQLite in production
            if is_production():
                print("[WARNING] Using SQLite in production environment. PostgreSQL is recommended for production deployments.")
            
            async with engine.begin() as aconn:
                await aconn.exec_driver_sql("PRAGMA journal_mode=WAL;")
                await aconn.exec_driver_sql("PRAGMA synchronous=NORMAL;")
                await aconn.exec_driver_sql("PRAGMA foreign_keys=ON;")
    except Exception:
        pass

# ---------- Helpers ----------

LANG_MAP = {
    "english": "en_US", "en": "en_US", "en_us": "en_US", "english_us": "en_US",
    "hindi": "hi_IN", "hi": "hi_IN", "hi_in": "hi_IN", "hindi_in": "hi_IN",
    "spanish": "es_MX", "es": "es_MX", "es_mx": "es_MX", "spanish_mx": "es_MX",
}

AFFIRM_REGEX = re.compile(
    r'^\s*(yes|y|ok|okay|sure|sounds\s+good|go\s+ahead|please\s+proceed|proceed|confirm|finalize|do\s+it)\b',
    re.I
)

def _normalize_language(s: str | None) -> str | None:
    if not s:
        return None
    # Normalize key by removing non-alphanumeric chars except underscore
    key = re.sub(r'[^a-z_]', '', s.strip().lower().replace("-", "_").replace(" ", "_"))
    return LANG_MAP.get(key, s if "_" in s else None)

def _is_affirmation(text: str) -> bool:
    return bool(AFFIRM_REGEX.match(text or ""))

def _sanitize_user_input(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = text.strip()
    if len(text) > 2000:
        text = text[:2000]
    
    # Remove potentially harmful patterns (keep data intact for LLM processing)
    for pattern in [
        r"(?i)system\s*:",
        r"(?i)assistant\s*:",
        r"(?i)ignore\s+previous\s+instructions",
        r"(?i)forget\s+everything",
        r"(?i)act\s+as\s+if",
        r"\{\{\s*\{\{",
    ]:
        text = re.sub(pattern, " ", text)
    return text.strip()

def _classify_user_intent(message: str, current_state: str) -> str:
    """Enhanced intent classification for laypeople using natural language."""
    msg = (message or "").lower()
    
    # Business goals and use cases (laypeople language)
    if any(w in msg for w in ["discount", "sale", "offer", "promotion", "deal", "special", "coupon", "new product", "collection", "launch"]):
        return "business_goal_promotional"
    if any(w in msg for w in ["order", "confirm", "delivery", "shipping", "appointment", "reminder", "update", "status", "invoice", "payment"]):
        return "business_goal_transactional"
    if any(w in msg for w in ["welcome", "greeting", "new customer", "thank you", "birthday", "anniversary"]):
        return "business_goal_relationship"
    if any(w in msg for w in ["login", "password", "code", "verification", "otp", "security", "verify"]):
        return "business_goal_security"
    
    # Business types (help categorize)
    if any(w in msg for w in ["restaurant", "food", "cafe", "hotel", "booking"]):
        return "business_type_hospitality"
    if any(w in msg for w in ["shop", "store", "retail", "clothes", "shoes", "fashion"]):
        return "business_type_retail"
    if any(w in msg for w in ["doctor", "clinic", "appointment", "health", "medical"]):
        return "business_type_healthcare"
    if any(w in msg for w in ["salon", "beauty", "spa", "hair", "nails"]):
        return "business_type_beauty"
    
    # Journey-specific intents
    if any(w in msg for w in ["don't know", "not sure", "help me", "guide me", "you choose", "you decide"]):
        return "needs_guidance"
    if any(w in msg for w in ["example", "sample", "show me", "what does", "how does"]):
        return "wants_example"
    if any(w in msg for w in ["yes", "okay", "sounds good", "that's right", "correct", "perfect"]):
        return "confirmation"
    if any(w in msg for w in ["no", "not right", "different", "change", "wrong"]):
        return "correction"
    
    # Language preferences
    if any(w in msg for w in ["english", "hindi", "spanish", "language"]):
        return "language_selection"
    
    # Content creation
    if any(w in msg for w in ["write", "create", "make", "message", "text", "content"]):
        return "content_creation"
    
    # Completion signals
    if any(w in msg for w in ["done", "finish", "complete", "ready", "finalize", "looks good"]):
        return "completion"
    
    # Greeting/chitchat
    if any(w in msg for w in ["hello", "hi", "hey", "good morning", "good afternoon"]):
        return "greeting"
    
    return "general_inquiry"

def _determine_conversation_state(draft: Dict[str, Any], memory: Dict[str, Any]) -> str:
    has_category = bool(draft.get("category") or memory.get("category"))
    has_language = bool(draft.get("language") or memory.get("language_pref"))
    has_name = bool(draft.get("name"))
    has_body = any(
        isinstance(c, dict) and c.get("type") == "BODY" and (c.get("text") or "").strip()
        for c in (draft.get("components") or [])
    )
    if not has_category:
        return "need_category"
    if not has_language:
        return "need_language"
    if not has_name:
        return "need_name"
    if not has_body:
        return "need_body"
    return "ready_to_finalize"

def _validate_llm_response(response: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(response, dict):
        return {
            "agent_action": "ASK",
            "message_to_user": "Which template category do you want: MARKETING, UTILITY, or AUTHENTICATION?",
            "draft": None,
            "missing": ["category"],
            "final_creation_payload": None,
            "memory": None,
        }
    response.setdefault("agent_action", "ASK")
    response.setdefault("message_to_user", "Please tell me more about your template.")
    response.setdefault("draft", None)
    response.setdefault("missing", [])
    response.setdefault("final_creation_payload", None)
    response.setdefault("memory", {})

    if response["agent_action"] not in {"ASK","DRAFT","UPDATE","FINAL","CHITCHAT"}:
        response["agent_action"] = "ASK"

    def _has_body(d: Dict[str, Any]) -> bool:
        for comp in (d.get("components") or []):
            if isinstance(comp, dict) and comp.get("type") == "BODY" and (comp.get("text") or "").strip():
                return True
        return False

    # Only validate FINAL action payloads, trust LLM for other actions
    if response["agent_action"] == "FINAL":
        draft = response.get("final_creation_payload") or response.get("draft") or {}
        required = ["name", "language", "category"]
        missing_fields = [k for k in required if not draft.get(k)]
        if not _has_body(draft):
            missing_fields.append("body")

        # Only downgrade to ASK if truly missing critical fields
        if missing_fields:
            response["agent_action"] = "ASK"
            response["missing"] = missing_fields
            response["message_to_user"] = f"I still need: {', '.join(missing_fields)}. Please provide them to complete the template."
    
    # For non-FINAL actions, trust the LLM's missing calculation completely
    # Don't override what the LLM determined
    return response

def _slug(s_: str) -> str:
    s_ = (s_ or "").lower().strip()
    s_ = re.sub(r"[^a-z0-9_]+", "_", s_)
    return (re.sub(r"_+", "_", s_).strip("_") or "template")[:64]

def _sanitize_candidate(cand: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(cand, dict):
        return {}
    c = dict(cand)

    # strip leaked policy keys if model echoed them
    for k in ("required","component_types","button_types","body_required"):
        c.pop(k, None)

    # Auto-convert name to snake_case if it doesn't match pattern
    pattern = re.compile(r"^[a-z0-9_]{1,64}$")
    if "name" in c and isinstance(c["name"], str) and c["name"].strip():
        nm = c["name"].strip()
        if not pattern.match(nm):
            c["name"] = _slug(nm)
        else:
            c["name"] = nm
    if "language" in c:
        lang = _normalize_language(c.get("language"))
        if lang:
            c["language"] = lang
        else:
            c.pop("language", None)

    # Normalize category to uppercase
    if "category" in c and isinstance(c["category"], str) and c["category"].strip():
        cat = c["category"].strip().upper()
        if cat in ("MARKETING", "UTILITY", "AUTHENTICATION"):
            c["category"] = cat
        else:
            c.pop("category", None)

    # drop blank strings
    for k in ("name","language","category"):
        if k in c and isinstance(c[k], str) and not c[k].strip():
            c.pop(k, None)

    # components clean
    comps = c.get("components")
    if isinstance(comps, list):
        clean = []
        collected_buttons = []  # Collect individual button components
        
        for comp in comps:
            if not isinstance(comp, dict):
                continue
            t = (comp.get("type") or "").strip().upper()
            if t == "BODY":
                txt = (comp.get("text") or "").strip()
                if txt:
                    out = {"type": "BODY", "text": txt}
                    if "example" in comp:
                        out["example"] = comp["example"]
                    clean.append(out)
            elif t == "HEADER":
                fmt = (comp.get("format") or "").strip().upper()
                txt = (comp.get("text") or "").strip()
                if not fmt and txt:
                    fmt = "TEXT"
                if fmt == "TEXT" and txt:
                    clean.append({"type": "HEADER", "format": "TEXT", "text": txt})
                elif fmt in {"IMAGE","VIDEO","DOCUMENT"}:
                    item = {"type": "HEADER", "format": fmt}
                    if "example" in comp:
                        item["example"] = comp["example"]
                    clean.append(item)
            elif t == "FOOTER":
                txt = (comp.get("text") or "").strip()
                if txt:
                    clean.append({"type":"FOOTER","text":txt})
            elif t == "BUTTONS":
                btns = comp.get("buttons")
                if isinstance(btns, list) and btns:
                    # Standard format: BUTTONS component with buttons array
                    b2 = []
                    for b in btns:
                        if not isinstance(b, dict):
                            continue
                        
                        # Handle different text field variations from LLM
                        btn_text = b.get("text") or b.get("label") or b.get("title")
                        btn_type = b.get("type", "QUICK_REPLY")
                        
                        if not btn_text:
                            continue
                            
                        # Normalize button structure
                        btn = {"type": btn_type, "text": btn_text}
                        
                        # Preserve payload for quick replies
                        payload = b.get("payload")
                        if payload:
                            btn["payload"] = payload
                        
                        # Add required fields for specific button types
                        if btn_type == "URL":
                            url = b.get("url")
                            if not url:
                                continue
                            btn["url"] = url
                        elif btn_type == "PHONE_NUMBER":
                            phone = b.get("phone_number")
                            if not phone:
                                continue
                            btn["phone_number"] = phone
                            
                        b2.append(btn)
                    if b2:
                        clean.append({"type":"BUTTONS","buttons": b2})
                elif comp.get("text") or comp.get("label") or comp.get("title"):
                    # Malformed format: Individual BUTTONS component with text/label/title
                    # Collect these to convert to proper format
                    btn_text = (comp.get("text") or comp.get("label") or comp.get("title") or "").strip()
                    btn_type = comp.get("button_type") or "QUICK_REPLY"
                    if btn_text:
                        btn = {"type": btn_type, "text": btn_text}
                        # Preserve payload for collected buttons too
                        payload = comp.get("payload")
                        if payload:
                            btn["payload"] = payload
                        collected_buttons.append(btn)
        
        # Convert collected individual buttons to proper BUTTONS component
        if collected_buttons:
            clean.append({"type": "BUTTONS", "buttons": collected_buttons})
                        
        if clean:
            c["components"] = clean
        else:
            c.pop("components", None)
    elif "components" in c:
        c.pop("components", None)
    
    # Convert flat fields to proper component structures
    # This handles cases where LLM outputs {BODY: "text"} or {body: "text"} instead of {components: [{type: "BODY", text: "text"}]}
    components = c.get("components", [])
    
    # Handle flat BODY field (try both cases)
    body_value = c.get("BODY") or c.get("body")
    if body_value and isinstance(body_value, str) and body_value.strip():
        body_text = body_value.strip()
        # Check if BODY component already exists
        has_body = any(comp.get("type") == "BODY" for comp in components if isinstance(comp, dict))
        if not has_body:
            components.insert(0, {"type": "BODY", "text": body_text})
        c.pop("BODY", None)  # Remove flat fields
        c.pop("body", None)
    
    # Handle flat HEADER field (try both cases) 
    header_value = c.get("HEADER") or c.get("header")
    if header_value and isinstance(header_value, str) and header_value.strip():
        header_text = header_value.strip()
        has_header = any(comp.get("type") == "HEADER" for comp in components if isinstance(comp, dict))
        if not has_header:
            components.append({"type": "HEADER", "format": "TEXT", "text": header_text})
        c.pop("HEADER", None)
        c.pop("header", None)
    
    # Handle flat FOOTER field (try both cases)
    footer_value = c.get("FOOTER") or c.get("footer")
    if footer_value and isinstance(footer_value, str) and footer_value.strip():
        footer_text = footer_value.strip()
        has_footer = any(comp.get("type") == "FOOTER" for comp in components if isinstance(comp, dict))
        if not has_footer:
            components.append({"type": "FOOTER", "text": footer_text})
        c.pop("FOOTER", None)
        c.pop("footer", None)
    
    # Update components if we added any
    if components:
        c["components"] = components
    
    return c

def _has_component(p: Dict[str, Any], kind: str) -> bool:
    return any(
        isinstance(c, dict) and (c.get("type") or "").upper() == kind
        for c in (p.get("components") or [])
    )

def _compute_missing(p: Dict[str, Any], memory: Dict[str, Any]) -> List[str]:
    miss: List[str] = []
    if not p.get("category"): miss.append("category")
    if not p.get("language"): miss.append("language")
    if not p.get("name"):     miss.append("name")
    comps = p.get("components") or []
    has_body = any(
        isinstance(c, dict) and (c.get("type") or "").upper() == "BODY" and (c.get("text") or "").strip()
        for c in comps
    )
    if not has_body: miss.append("body")
    
    # Extras only when allowed AND not skipped
    cat = (p.get("category") or memory.get("category") or "").upper()
    skip_extras = (memory.get("extras_choice") == "skip")
    if cat != "AUTHENTICATION" and not skip_extras:
        if memory.get("wants_header") and not _has_component(p, "HEADER"):
            miss.append("header")
        if memory.get("wants_footer") and not _has_component(p, "FOOTER"):
            miss.append("footer")
        if memory.get("wants_buttons") and not _has_component(p, "BUTTONS"):
            miss.append("buttons")
    return miss

def _minimal_scaffold(mem: Dict[str, Any]) -> Dict[str, Any]:
    cat = (mem.get("category") or "").upper()
    if cat not in {"MARKETING","UTILITY","AUTHENTICATION"}:
        return {}
    lang = mem.get("language_pref") or mem.get("language") or "en_US"
    event = mem.get("event_label") or mem.get("event") or "offer"
    business = mem.get("business_type") or mem.get("business") or "brand"
    name = mem.get("proposed_name") or f"{_slug(event)}_{_slug(business)}_v{dt.datetime.utcnow().strftime('%m%d')}"
    components: List[Dict[str, Any]] = []
    if cat == "AUTHENTICATION":
        body = "{{1}} is your verification code. Do not share this code. It expires in {{2}} minutes."
        components.append({"type":"BODY","text":body})
        return {"category":cat,"language":lang,"name":name,"components":components}
    body = "Hi {{1}}, {event}! Enjoy {{2}}.".format(event=event)
    if cat == "UTILITY":
        body = "Hello {{1}}, your {{2}} has been updated. Latest status: {{3}}."
    components.append({"type":"BODY","text":body})
    return {"category":cat,"language":lang,"name":name,"components":components}

def _fallback_reply_for_state(state: str) -> str:
    if state == "need_category":
        return "Which template type do you want: MARKETING, UTILITY, or AUTHENTICATION?"
    if state == "need_language":
        return "Which language code should I use (e.g., en_US, hi_IN)?"
    if state == "need_name":
        return "What should we name this template (snake_case)?"
    if state == "need_body":
        return "What should the main message (BODY) say?"
    return "Could you please rephrase what you want to create?"

def _user_declined_extras(msg: str) -> bool:
    t = (msg or "").lower()
    return any(phrase in t for phrase in [
        "skip", "no buttons", "no header", "no footer",
        "finalize as is", "looks good as is", "no extras"
    ])

def _auto_apply_extras_on_yes(user_text: str, candidate: Dict[str, Any], memory: Dict[str, Any]) -> Dict[str, Any]:
    """If user affirms and they asked for extras, auto-add compliant components."""
    if not _is_affirmation(user_text):
        return candidate or {}
    cand = dict(candidate or {})
    comps = list((cand.get("components") or []))

    # block extras for AUTHENTICATION
    cat = (memory.get("category") or cand.get("category") or "").upper()
    if cat == "AUTHENTICATION":
        return cand

    def has(kind: str) -> bool:
        return any(isinstance(c, dict) and (c.get("type") or "").upper() == kind for c in comps)

    changed = False
    if memory.get("wants_header") and not has("HEADER"):
        hdr = (memory.get("event_label") or "Special offer just for you!")[:60]
        comps.insert(0, {"type": "HEADER", "format": "TEXT", "text": hdr})
        changed = True
    if memory.get("wants_footer") and not has("FOOTER"):
        comps.append({"type":"FOOTER","text":"Thank you!"})
        changed = True
    if memory.get("wants_buttons") and not has("BUTTONS"):
        comps.append({
            "type":"BUTTONS",
            "buttons":[
                {"type":"QUICK_REPLY","text":"View offers"},
                {"type":"QUICK_REPLY","text":"Order now"}
            ]
        })
        changed = True
    if changed:
        cand["components"] = comps
    return cand

def _strip_non_schema_button_fields(candidate: Dict[str, Any]) -> None:
    """Strip non-schema fields from buttons before validation (e.g., payload)"""
    allowed = {
        "QUICK_REPLY": {"type", "text"},
        "URL": {"type", "text", "url"},
        "PHONE_NUMBER": {"type", "text", "phone_number"},
    }
    for comp in (candidate.get("components") or []):
        if (comp.get("type") or "").upper() == "BUTTONS" and isinstance(comp.get("buttons"), list):
            for b in comp["buttons"]:
                t = (b.get("type") or "QUICK_REPLY").upper()
                for k in list(b.keys()):
                    if k not in allowed.get(t, set()):
                        b.pop(k, None)

def _strip_component_extras(candidate: Dict[str, Any]) -> None:
    """Strip non-schema fields from components before validation"""
    allowed = {
        "BODY": {"type", "text", "example"},      # Keep example for BODY if schema allows
        "HEADER": {"type", "format", "text", "example"},  # Keep example for HEADER if schema allows
        "FOOTER": {"type", "text"},
        "BUTTONS": {"type", "buttons"},
    }
    for comp in (candidate.get("components") or []):
        t = (comp.get("type") or "").upper()
        keep = allowed.get(t)
        if keep:
            for k in list(comp.keys()):
                if k not in keep:
                    comp.pop(k, None)

def _targeted_missing_reply(missing: List[str], memory: Dict[str, Any] = None) -> str:
    # Handle AUTH constraint for buttons
    if "buttons" in missing and memory and (memory.get("category") or "").upper() == "AUTHENTICATION":
        return "Buttons aren't allowed for authentication templates; I'll proceed without them. Want a short TEXT header?"
    
    # Pick the highest-priority missing slot and ask a focused question
    if "language" in missing:
        return "Great so far. Which language code should I use (e.g., en_US, hi_IN)?"
    if "name" in missing:
        return "What should we name this template? Use snake_case (e.g., diwali_sweets_offer)."
    if "body" in missing:
        return "What should the main message (BODY) say? If you want, I can write it for you."
    if "category" in missing:
        return "Which template category should I use: MARKETING, UTILITY, or AUTHENTICATION?"
    if "header" in missing:
        return "You asked for a header. Should I add a short TEXT header like 'Festive offer just for you!'?"
    if "buttons" in missing:
        return "You asked for buttons. Should I add two quick replies like 'View offers' and 'Order now'?"
    if "footer" in missing:
        return "You asked for a footer. Should I add a short footer like 'Thank you!'?"
    return "What would you like me to add next?"

# ---------- Endpoints ----------





# ---------- Endpoints ----------

@app.post("/chat", response_model=ChatResponse)
async def chat(inp: ChatInput, db: AsyncSession = Depends(get_db)):
    cfg = get_config()
    hist_cfg = cfg.get("history", {}) or {}
    max_turns = int(hist_cfg.get("max_turns", 200))

    # 1) Load/create session + draft
    s = await get_or_create_session(db, inp.session_id)
    if not s.active_draft_id:
        d = await create_draft(db, s.id, draft={}, version=1)
        s.active_draft_id = d.id
        await db.flush()
    else:
        d = await db.get(Draft, s.active_draft_id)
        if d is None:
            d = await create_draft(db, s.id, draft={}, version=1)
            s.active_draft_id = d.id
            await db.flush()

    draft: Dict[str, Any] = dict(d.draft or {})
    memory: Dict[str, Any] = dict(s.memory or {})
    msgs: List[Dict[str, str]] = (s.data or {}).get("messages", [])

    # 2) Build LLM inputs + call
    # Use friendly system prompt for better user experience
    system = build_friendly_system_prompt(cfg)
    context = build_context_block(draft, memory, cfg, msgs)
    safe_message = _sanitize_user_input(inp.message)

    # Track explicit extras requests so we block FINAL until they exist
    lower_msg = safe_message.lower()
    if "header" in lower_msg:
        memory["wants_header"] = True
    if "footer" in lower_msg:
        memory["wants_footer"] = True
    if "button" in lower_msg or "buttons" in lower_msg:
        memory["wants_buttons"] = True
    s.memory = memory

    current_state = _determine_conversation_state(draft, memory)
    user_intent = _classify_user_intent(safe_message, current_state)
    memory["_system_state"] = current_state
    memory["_user_intent"] = user_intent
    
    # Track journey stage for friendly prompts
    journey_stage = _get_journey_stage_from_memory(memory)
    memory["_journey_stage"] = journey_stage
    
    # Check for explicit content provision
    explicit_content = _extract_explicit_content(safe_message)
    if explicit_content:
        memory["user_provided_content"] = explicit_content
        memory["content_extraction_hint"] = f"User provided: {explicit_content[:50]}..."
    
    s.memory = memory

    # Auto-name session if this is the first message and user_id is provided
    if inp.user_id and len(msgs) == 0:
        from sqlalchemy import select
        user = (await db.execute(select(User).where(User.user_id == inp.user_id))).scalar_one_or_none()
        if user:
            # Ensure the association exists, then auto-name
            await upsert_user_session(db, inp.user_id, s.id, None)
            category = memory.get("category") or draft.get("category")
            await _auto_name_session_if_needed(db, inp.user_id, s.id, safe_message, category)

    llm = LlmClient(model=cfg.get("model", "gpt-4o-mini"),
                    temperature=float(cfg.get("temperature", 0.2)))

    # Log request before calling LLM for better failure trails
    # Use scrubbed data for logging only (preserve sensitive data for LLM processing)
    log_user = scrub_sensitive_data(safe_message)
    request_payload = {"system": system, "context": context, "history": msgs,
                      "user": log_user, "state": current_state, "intent": user_intent}
    await log_llm(db, s.id, "request", _redact_secrets(request_payload), cfg.get("model"), None)

    try:
        out = llm.respond(system, context, msgs, safe_message)
        out = _validate_llm_response(out)
    except Exception as e:
        error_payload = {"error": str(e), "user_input": scrub_sensitive_data(safe_message)}
        await log_llm(db, s.id, "error", _redact_secrets(error_payload), cfg.get("model"), None)
        fallback = _fallback_reply_for_state(current_state)
        await db.commit()  # ensure any earlier inserts/updates (e.g., user_session) persist
        return ChatResponse(session_id=s.id, reply=fallback,
                            draft=draft, missing=_compute_missing(draft, memory),
                            final_creation_payload=None)

    # Log response
    await log_llm(db, s.id, "response", _redact_secrets(out), cfg.get("model"), out.get("_latency_ms"))

    # 3) Extract outputs
    action = str(out.get("agent_action") or "ASK").upper()
    reply = (out.get("message_to_user") or "").strip()
    candidate = out.get("final_creation_payload") or out.get("draft") or {}
    mem_update = out.get("memory") or {}
    if mem_update:
        memory = merge_deep(memory, mem_update)
        s.memory = memory
    if _user_declined_extras(safe_message):
        memory = merge_deep(memory, {"extras_choice": "skip"})
        # Clear any pending extras to avoid repeated prompts
        for k in ("wants_header", "wants_footer", "wants_buttons"):
            memory.pop(k, None)
        s.memory = memory

    # local history helper
    def _append_history(user_text: str, assistant_text: str) -> List[Dict[str, str]]:
        new_hist = msgs + [{"role": "user", "content": user_text},
                           {"role": "assistant", "content": assistant_text}]
        return new_hist[-max_turns:]

    # 5) Let the LLM drive category; don't inject server question
    category = (candidate.get("category") or memory.get("category") or draft.get("category"))
    if category and not memory.get("category"):
        s.memory = merge_deep(memory, {"category": category})

    # Helper to persist a turn
    async def _persist_turn_and_return(reply_text: str, new_draft: Dict[str, Any], missing_list: List[str]):
        s.last_action = action
        # Track question hash to break repeats
        s.last_question_hash = _qhash(reply_text) if reply_text.endswith("?") else None
        s.data = {**(s.data or {}), "messages": _append_history(inp.message, reply_text)}
        await touch_user_session(db, inp.user_id, s.id)
        await upsert_session(db, s); await db.commit()
        return ChatResponse(session_id=s.id, reply=reply_text, draft=new_draft,
                            missing=missing_list, final_creation_payload=None)

    # 6) Non-FINAL → merge sanitized candidate (with extras auto-apply on "yes")
    if action in {"ASK","DRAFT","UPDATE","CHITCHAT"}:
        candidate = _auto_apply_extras_on_yes(safe_message, candidate, memory)
        cand_clean = _sanitize_candidate(candidate) if candidate else {}
        merged = merge_deep(draft, cand_clean) if cand_clean else draft

        # opportunistic language normalization from the message
        if not merged.get("language"):
            lang_guess = _normalize_language(safe_message)
            if lang_guess:
                merged["language"] = lang_guess

        d.draft = merged

        # Trust LLM for guidance but correct it with actual state
        llm_missing = (out.get("missing") or [])
        computed_missing = _compute_missing(merged, memory)

        # Remove extras that we already applied/present now
        extras_present = {
            "header": _has_component(merged, "HEADER"),
            "buttons": _has_component(merged, "BUTTONS"),
            "footer": _has_component(merged, "FOOTER"),
        }
        llm_missing = [
            m for m in llm_missing
            if m not in ("header", "buttons", "footer") or not extras_present.get(m, False)
        ]

        # Keep only the core fields from server if LLM forgot them
        core = [m for m in computed_missing if m in ["category", "language", "name", "body"]]
        missing = list(dict.fromkeys(llm_missing + core))

        # Mark success in memory after applying extras
        if any(extras_present.values()):
            memory = merge_deep(memory, {"extras_choice": "accepted"})
            s.memory = memory

        final_reply = (reply or _targeted_missing_reply(missing, memory)).strip()

        # Add encouragement and examples from friendly_prompts when appropriate
        if len(msgs) > 0 and any(extras_present.values()):
            import random
            encouragement = random.choice(get_encouragement_messages())
            final_reply = f"{encouragement} {final_reply}"
        
        # Provide helpful examples if user seems stuck
        if "example" in safe_message.lower() or "sample" in safe_message.lower():
            category = merged.get("category") or memory.get("category")
            if category:
                examples = get_helpful_examples()
                category_examples = examples.get(f"{category.lower()}_examples", [])
                if category_examples:
                    example = random.choice(category_examples)
                    final_reply += f"\n\nHere's an example: {example}"

        if _has_component(merged, "BUTTONS") and "button" in (final_reply.lower()):
            # Replace the stale question with a confirmation
            final_reply = "Added two quick replies (View offers / Order now). Anything else to add?"
        if extras_present["header"] and "header" in final_reply.lower():
            final_reply = "Added a short TEXT header. Anything else to add?"
        if extras_present["footer"] and "footer" in final_reply.lower():
            final_reply = "Added a short footer. Anything else to add?"
        return await _persist_turn_and_return(final_reply, merged, missing)

    # 7) FINAL → sanitize -> validate -> persist (also enforce requested extras)
    if action == "FINAL":
        candidate = _auto_apply_extras_on_yes(safe_message, candidate, memory)
        cand_clean = _sanitize_candidate(candidate) if candidate else {}
        candidate = cand_clean or draft or _minimal_scaffold(memory)

        def _has_component_kind(p: Dict[str, Any], kind: str) -> bool:
            return any(isinstance(c, dict) and (c.get("type") or "").upper() == kind for c in (p.get("components") or []))

        # enforce requested extras before validate (only for non-AUTH categories)
        missing_extras = []
        cat = (candidate.get("category") or memory.get("category") or "").upper()
        if cat != "AUTHENTICATION":
            if memory.get("wants_header") and not _has_component_kind(candidate, "HEADER"):
                missing_extras.append("header")
            if memory.get("wants_footer") and not _has_component_kind(candidate, "FOOTER"):
                missing_extras.append("footer")
            if memory.get("wants_buttons") and not _has_component_kind(candidate, "BUTTONS"):
                missing_extras.append("buttons")

        if missing_extras:
            d.draft = merge_deep(draft, candidate)
            s.last_action = "ASK"
            ask = _targeted_missing_reply(missing_extras, memory)
            s.data = {**(s.data or {}), "messages": _append_history(inp.message, ask)}
            await touch_user_session(db, inp.user_id, s.id)
            await upsert_session(db, s); await db.commit()
            return ChatResponse(session_id=s.id, reply=ask, draft=d.draft,
                                missing=_compute_missing(d.draft, memory),
                                final_creation_payload=None)

        schema = cfg.get("creation_payload_schema", {}) or {}
        # Validate a deep copy to preserve rich draft data (e.g., button payloads)
        import copy
        candidate_for_validation = copy.deepcopy(candidate)
        _strip_component_extras(candidate_for_validation)
        _strip_non_schema_button_fields(candidate_for_validation)
        issues = validate_schema(candidate_for_validation, schema)
        issues += lint_rules(candidate_for_validation, cfg.get("lint_rules", {}) or {})

        if issues:
            d.draft = merge_deep(draft, candidate)  # keep rich draft
            s.last_action = "ASK"
            final_reply = (reply + ("\n\nPlease fix: " + "; ".join(issues) if issues else "")).strip()
            s.data = {**(s.data or {}), "messages": _append_history(inp.message, final_reply)}
            await touch_user_session(db, inp.user_id, s.id)
            await upsert_session(db, s); await db.commit()
            return ChatResponse(session_id=s.id, reply=final_reply, draft=d.draft,
                                missing=_compute_missing(d.draft, memory) + ["fix_validation_issues"],
                                final_creation_payload=None)

        # Valid → finalize
        d.finalized_payload = candidate_for_validation  # schema-pure for WhatsApp API
        d.status = "FINAL"
        d.draft = candidate  # keep rich draft for UI
        s.last_action = "FINAL"
        s.data = {**(s.data or {}), "messages": _append_history(inp.message, reply or "Finalized.")}
        await touch_user_session(db, inp.user_id, s.id)
        await upsert_session(db, s); await db.commit()
        return ChatResponse(session_id=s.id, reply=reply or "Finalized.", draft=d.draft,
                            missing=None, final_creation_payload=candidate_for_validation)

    # 8) Fallback (treat as ASK)
    final_draft = candidate or draft
    d.draft = final_draft
    s.last_action = "ASK"
    missing = _compute_missing(final_draft, memory)
    final_reply = (reply or _targeted_missing_reply(missing, memory)).strip()

    # anti-loop: if same question and user affirmed, proactively fill one slot
    if final_reply.endswith("?"):
        qh = _qhash(final_reply)
        if s.last_question_hash == qh and _is_affirmation(safe_message):
            base = dict(final_draft)  # <-- avoid using undefined 'merged'
            base = merge_deep(base, _auto_apply_extras_on_yes(safe_message, {}, memory))
            if "language" in missing:
                base["language"] = _normalize_language(safe_message) or memory.get("language_pref") or "en_US"
            if "name" in missing and any(k in safe_message.lower() for k in ["you choose","suggest","pick a name"]):
                base["name"] = _slug(memory.get("event_label") or "template")
            if "body" in missing and "you choose" in safe_message.lower():
                base.setdefault("components", []).insert(0, {"type": "BODY", "text": "Hi {{1}}, we have a special offer for you!"})
            d.draft = base
            final_draft = base
            missing = _compute_missing(final_draft, memory)
            final_reply = _targeted_missing_reply(missing, memory)
        s.last_question_hash = qh
    else:
        s.last_question_hash = None

    s.data = {**(s.data or {}), "messages": _append_history(inp.message, final_reply)}
    await touch_user_session(db, inp.user_id, s.id)
    await upsert_session(db, s); await db.commit()
    return ChatResponse(session_id=s.id, reply=final_reply, draft=final_draft,
                        missing=missing, final_creation_payload=None)

@app.get("/welcome")
async def get_welcome_message():
    """
    Get a friendly welcome message for new users starting their template creation journey.
    Perfect for showing in the UI before the first chat interaction.
    """
    from .friendly_prompts import get_journey_welcome_message, get_helpful_examples
    
    # Get examples from friendly prompts
    examples_data = get_helpful_examples()
    
    return {
        "message": get_journey_welcome_message(),
        "journey_stage": "welcome",
        "next_steps": [
            "Tell me what kind of message you want to send",
            "Describe your business or use case", 
            "Let me know your goal in simple words"
        ],
        "examples": [
            "I want to send discount offers to my customers",
            "I need to confirm orders for my restaurant",
            "I want to send appointment reminders", 
            "I'd like to welcome new customers"
        ],
        "sample_templates": {
            "marketing": examples_data.get("marketing_examples", [])[:2],
            "utility": examples_data.get("utility_examples", [])[:2],
            "authentication": examples_data.get("authentication_examples", [])[:1]
        }
    }

# ---------- Helper Functions ----------

def _get_business_examples_for_category(category: str) -> list:
    """Get relatable business examples for different template categories."""
    examples = {
        "MARKETING": [
            "🛍️ Clothing store sending discount offers",
            "🍕 Restaurant promoting new menu items", 
            "💄 Beauty salon announcing special packages",
            "📱 Electronics store with sale notifications"
        ],
        "UTILITY": [
            "📦 E-commerce order confirmations",
            "🏥 Medical appointment reminders",
            "🚗 Service center status updates", 
            "💳 Payment confirmation messages"
        ],
        "AUTHENTICATION": [
            "🔐 Login verification codes",
            "📱 Account security confirmations",
            "🛡️ Two-factor authentication codes"
        ]
    }
    return examples.get(category, [])

def _generate_beginner_friendly_name(user_input: str, business_type: str = "", category: str = "") -> str:
    """Generate template names that make sense to beginners."""
    user_lower = user_input.lower()
    
    # Extract key concepts
    if "discount" in user_lower or "offer" in user_lower or "sale" in user_lower:
        base = "discount_offer"
    elif "welcome" in user_lower or "greeting" in user_lower:
        base = "welcome_message"
    elif "appointment" in user_lower or "reminder" in user_lower:
        base = "appointment_reminder"
    elif "order" in user_lower or "confirmation" in user_lower:
        base = "order_confirmation"
    elif "birthday" in user_lower or "special day" in user_lower:
        base = "birthday_wishes"
    elif "new product" in user_lower or "launch" in user_lower:
        base = "new_product_launch"
    else:
        # Fallback based on category
        if category == "MARKETING":
            base = "promotional_message"
        elif category == "UTILITY":
            base = "notification_message"
        elif category == "AUTHENTICATION":
            base = "verification_code"
        else:
            base = "business_message"
    
    # Add business context if available
    if business_type:
        business_slug = _slug(business_type)
        base = f"{business_slug}_{base}"
    
    return base

def _provide_content_suggestions(category: str, business_type: str = "", user_goal: str = "") -> list:
    """Provide content suggestions based on user's business and goals."""
    suggestions = []
    
    if category == "MARKETING":
        suggestions = [
            "Hi {{1}}! 🎉 Special offer just for you - 20% off everything! Use code SAVE20. Shop now!",
            "Hello {{1}}! New arrivals are here! Be the first to see our latest {{2}} collection. Visit us today!",
            "Hey {{1}}! Flash sale alert! Get {{2}} at amazing prices. Limited time only! 🔥"
        ]
    elif category == "UTILITY":
        suggestions = [
            "Hi {{1}}! Your order #{{2}} has been confirmed. Expected delivery: {{3}}. Track anytime!",
            "Hello {{1}}! Appointment reminder for {{2}} at {{3}}. Looking forward to seeing you!",
            "Hi {{1}}! Your {{2}} has been updated. New status: {{3}}. Thanks for choosing us!"
        ]
    elif category == "AUTHENTICATION":
        suggestions = [
            "Your verification code is {{1}}. Enter this code to complete login. Expires in {{2}} minutes.",
            "Security code: {{1}}. Use this to verify your account. Never share this code. Valid for {{2}} minutes."
        ]
    
    return suggestions

def _get_journey_stage_from_memory(memory: dict) -> str:
    """Determine what stage of the journey the user is in."""
    if not memory.get("category") and not memory.get("business_type"):
        return "welcome"
    elif memory.get("business_type") and not memory.get("category"):
        return "choose_type"
    elif memory.get("category") and not memory.get("proposed_content"):
        return "create_content"
    elif memory.get("proposed_content") and not memory.get("extras_offered"):
        return "add_extras"
    else:
        return "review"

def _extract_explicit_content(message: str) -> str:
    """Extract explicit content when user provides it directly."""
    msg = message.strip()
    
    # Common patterns users use to provide content
    patterns = [
        r"the message should say:?\s*(.+)",
        r"the message is:?\s*(.+)", 
        r"message content:?\s*(.+)",
        r"the text should be:?\s*(.+)",
        r"here'?s the message:?\s*(.+)",
        r"use this message:?\s*(.+)",
        r"send this:?\s*(.+)",
        r"say:?\s*(.+)",
    ]
    
    import re
    for pattern in patterns:
        match = re.search(pattern, msg, re.IGNORECASE | re.DOTALL)
        if match:
            content = match.group(1).strip()
            # Remove quotes if present
            if (content.startswith('"') and content.endswith('"')) or \
               (content.startswith("'") and content.endswith("'")):
                content = content[1:-1]
            return content
    
    return ""


