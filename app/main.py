from __future__ import annotations
from typing import Dict, Any, List
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.engine.url import make_url
import os
import re
import datetime as dt
import copy
import random

from .db import engine, SessionLocal, Base
from .models import Draft, User, UserSession
from .repo import get_or_create_session, upsert_session, create_draft, log_llm, upsert_user_session, touch_user_session, get_user_business_profile, upsert_user_business_profile
from .config import get_config, get_cors_origins, is_production
from .prompts import build_system_prompt, build_context_block, build_friendly_system_prompt
from .llm import LlmClient
from .validator import validate_schema, lint_rules
from .schemas import ChatInput, ChatResponse, SessionData, ChatMessage
from .utils import merge_deep, scrub_sensitive_data
from .friendly_prompts import get_encouragement_messages, get_helpful_examples

# Import route modules
from .routes import config, debug, users, sessions

# Guard interactive router import
try:
    from .interactive import router as interactive_router
    INTERACTIVE_AVAILABLE = True
except ImportError:
    INTERACTIVE_AVAILABLE = False
    interactive_router = None

app = FastAPI(title="LLM-First WhatsApp Template Builder", version="4.0.0")

# Include route modules
app.include_router(config.router)
app.include_router(debug.router)
app.include_router(users.router)
app.include_router(sessions.router)

# Include interactive router if available
if INTERACTIVE_AVAILABLE and interactive_router:
    app.include_router(interactive_router)

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

# Button normalization constants
MAX_BUTTONS = 3

def _cap_buttons(buttons: list[dict]) -> list[dict]:
    """Deduplicate buttons by text (case-insensitive), enforce 20-char limit, and cap at MAX_BUTTONS."""
    seen = set()
    out = []
    for b in buttons:
        if not isinstance(b, dict):
            continue
        
        # Create key for deduplication and enforce text length limit
        btn_text = (b.get("text") or "").strip()[:20]
        btn_type = (b.get("type") or "QUICK_REPLY").upper()
        key = (btn_type, btn_text.lower())
        
        if not btn_text or key in seen:
            continue
            
        seen.add(key)
        # Create a copy with enforced text length
        btn_copy = dict(b)
        btn_copy["text"] = btn_text
        out.append(btn_copy)
        
        if len(out) >= MAX_BUTTONS:
            break
    
    return out

# --- CORS configuration based on environment ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

async def get_db():
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
    r'^\s*(yes|y|ok|okay|sure|sounds\s+good|go\s+ahead|please\s+proceed|proceed|confirm|finalize|do\s+it|yeah|yep|yup|go\s+for\s+it|let\'s\s+do\s+it|absolutely|alright|looks\s+good)\b',
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
            if isinstance(comp, dict) and (comp.get("type") or "").upper() == "BODY" and (comp.get("text") or "").strip():
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
            
            # Create friendly, specific guidance instead of robotic listing
            if "body" in missing_fields and len(missing_fields) == 1:
                # Special case: only body missing but we have BODY component
                if _has_body(draft):
                    # BODY component exists, so complete the template
                    response["agent_action"] = "FINAL"
                    response["final_creation_payload"] = draft
                    response["message_to_user"] = "Perfect! 🎉 Your template is complete and ready to use. I've captured all your details including your message about the chocolate cake promotion!"
                    response["missing"] = []
                else:
                    response["message_to_user"] = "Great progress! 😊 I just need the main message content. What should your template say to customers?"
            elif len(missing_fields) == 1:
                field = missing_fields[0]
                if field == "name":
                    response["message_to_user"] = "Almost done! 🌟 What would you like to name this template? (e.g., 'chocolate_cake_promo')"
                elif field == "language":
                    response["message_to_user"] = "Just one more thing! What language should this be in? English, Spanish, or Hindi?"
                elif field == "category":
                    response["message_to_user"] = "Perfect! Is this a marketing promotion, a utility message (like confirmations), or an authentication code?"
                else:
                    response["message_to_user"] = f"Almost there! 🎯 I just need the {field}. Could you help me with that?"
            else:
                # Multiple fields missing
                friendly_fields = []
                for field in missing_fields:
                    if field == "body":
                        friendly_fields.append("main message content")
                    elif field == "name":
                        friendly_fields.append("template name")
                    elif field == "language":
                        friendly_fields.append("language")
                    elif field == "category":
                        friendly_fields.append("message type (marketing/utility/authentication)")
                    else:
                        friendly_fields.append(field)
                
                if len(friendly_fields) == 2:
                    response["message_to_user"] = f"Great start! 😊 I just need the {friendly_fields[0]} and {friendly_fields[1]} to complete your template."
                else:
                    response["message_to_user"] = f"Excellent progress! 🌟 To finish your template, I need: {', '.join(friendly_fields[:-1])}, and {friendly_fields[-1]}."
    
    # For non-FINAL actions, trust the LLM's missing calculation completely
    # Don't override what the LLM determined
    return response

def _slug(s_: str) -> str:
    s_ = (s_ or "").lower().strip()
    s_ = re.sub(r"[^a-z0-9_]+", "_", s_)
    return (re.sub(r"_+", "_", s_).strip("_") or "template")[:64]

# --- NLP-powered directive parsing engine ---
URL_RE   = re.compile(r"(https?://[^\s]+)", re.I)
PHONE_RE = re.compile(r"(\+?[\d\-\s().]{10,})", re.I)  # More restrictive to avoid false positives

def _syn(cfg, key) -> list[str]:
    """Get synonym list for a key from config."""
    return [s.lower() for s in (((cfg.get("nlp") or {}).get("synonyms") or {}).get(key) or [])]

def _tokenize(text: str) -> list[str]:
    """Tokenize text for intent matching."""
    return re.findall(r"[A-Za-z0-9_+:/.-]+", (text or "").lower())

def _default_quick_replies(cfg: Dict[str,Any], category: str, brand: str = "", business_context: str = "") -> list[dict]:
    """Get contextually relevant quick reply buttons for a category and business."""
    cat = (category or "").upper()
    
    # First, try to get business-specific buttons
    if brand or business_context:
        business_type = _detect_business_type(brand, business_context)
        specific_buttons = _get_business_specific_buttons(business_type, cat)
        if specific_buttons:
            return specific_buttons
    
    # Fallback to config defaults - fix path to lint_rules.components
    lint_rules = cfg.get("lint_rules", {})
    components = lint_rules.get("components", {})
    buttons_config = components.get("buttons", {})
    defaults_by_cat = buttons_config.get("defaults_by_category", {})
    
    labels = defaults_by_cat.get(cat, defaults_by_cat.get("MARKETING", ["Shop now", "Learn more", "Contact us"]))
    labels = [str(x).strip()[:20] for x in labels if str(x).strip()]
    return [{"type":"QUICK_REPLY","text":lbl} for lbl in labels[:MAX_BUTTONS]]

def _detect_business_type(brand: str, context: str) -> str:
    """Detect business type from brand name and context."""
    text = f"{brand} {context}".lower()
    
    # More specific detection patterns
    if any(word in text for word in ["sweet", "candy", "dessert", "bakery", "cake", "mithai", "confection"]):
        return "sweets"
    elif any(word in text for word in ["restaurant", "cafe", "food", "kitchen", "dining", "eatery"]):
        return "restaurant" 
    elif any(word in text for word in ["clinic", "doctor", "medical", "health", "hospital", "pharmacy"]):
        return "healthcare"
    elif any(word in text for word in ["salon", "beauty", "spa", "hair", "nails", "massage"]):
        return "beauty"
    elif any(word in text for word in ["shop", "store", "retail", "fashion", "clothes", "boutique"]):
        return "retail"
    elif any(word in text for word in ["service", "repair", "maintenance", "tech", "cleaning"]):
        return "services"
    else:
        return "general"

def _get_business_specific_buttons(business_type: str, category: str) -> list[dict]:
    """Get business-specific button suggestions."""
    buttons_map = {
        "sweets": {
            "MARKETING": ["Order sweets", "View menu", "Call store"],
            "UTILITY": ["Track order", "Reorder", "Contact us"],
        },
        "restaurant": {
            "MARKETING": ["Book table", "View menu", "Order now"],
            "UTILITY": ["Confirm booking", "Modify order", "Call restaurant"],
        },
        "healthcare": {
            "MARKETING": ["Book appointment", "Learn more", "Contact clinic"],
            "UTILITY": ["Reschedule", "Confirm appointment", "Call clinic"],
        },
        "beauty": {
            "MARKETING": ["Book appointment", "View services", "Special offers"],
            "UTILITY": ["Reschedule", "Confirm booking", "Contact salon"],
        },
        "retail": {
            "MARKETING": ["Shop now", "View catalog", "Get directions"],
            "UTILITY": ["Track order", "Return item", "Contact support"],
        },
        "services": {
            "MARKETING": ["Get quote", "Schedule visit", "Learn more"],
            "UTILITY": ["Reschedule", "Confirm service", "Contact us"],
        }
    }
    
    cat = category.upper()
    business_buttons = buttons_map.get(business_type, {})
    labels = business_buttons.get(cat, [])
    
    if not labels:
        return []
    
    # Meta UI cap for button titles is effectively ~20 chars. Trim here.
    labels = [str(x).strip()[:20] for x in labels if str(x).strip()]
    return [{"type":"QUICK_REPLY","text":lbl} for lbl in labels[:MAX_BUTTONS]]

def _extract_int(text: str) -> int | None:
    """Extract integer from text for length targets, counts, etc."""
    m = re.search(r"\b(\d{2,4})\b", text)
    return int(m.group(1)) if m else None

def _extract_brand_name(text: str) -> str | None:
    """Extract brand/company name from various patterns."""
    patterns = [
        # "company name as Sinch" / "add company name as Sinch"
        r"\b(?:company|brand)\s+name\s+(?:is|as|=)\s+(?P<brand>.+?)(?:\s+(?:in|for|and|with)\b|$)",
        # "my company is TechStart"
        r"\bmy\s+(?:company|brand)\s+(?:is|as|=)\s+(?P<brand>.+?)(?:\s+(?:in|for|and|with)\b|$)",
        # "use Sinch as company name"
        r"\b(?:use|set|add|include)\s+(?P<brand>.+?)\s+as\s+(?:company|brand)\s+name\b",
        # "add company name as Sinch"
        r"\b(?:add|include|insert)\s+(?:company|brand)\s+name\s+as\s+(?P<brand>.+?)(?:\s+(?:in|for|and|with)\b|$)",
        # "include Sinch as company name"
        r"\b(?:include|add)\s+(?P<brand>\w+(?:\s+\w+)*)\s+as\s+(?:company|brand)\s+name\b",
        # "include brand name Acme Corp" - fix for complex phrases
        r"\b(?:add|include)\s+(?:brand|company)\s+name\s+(?P<brand>\w+(?:\s+\w+)*)(?:\s+(?:in|for|and|with)\b|$)",
        # Generic "brand Acme" patterns
        r"\b(?:add|include)\s+(?:brand|company)\s+(?P<brand>\w+(?:\s+\w+)*)\b",
    ]
    txt = (text or "").strip()
    for pat in patterns:
        m = re.search(pat, txt, re.I)
        if m:
            brand = (m.group("brand") or "").strip(' """\'.,;!:')
            # Remove common trailing words that aren't part of brand name
            brand = re.split(r"\s+(?:in|for|and|with|to|as)\b", brand)[0].strip()
            # Filter out single words that are likely not brand names
            if brand and len(brand) > 1 and not re.match(r'^(name|brand|company)$', brand, re.I): 
                return brand[:60]
    
    # Look for quoted strings as fallback
    quoted = re.search(r'["""\'](.+?)["""\']', txt)
    if quoted and len(quoted.group(1)) > 1:
        return quoted.group(1)[:60].strip()
    
    return None

def _ensure_brand_in_body(components: list[dict], brand: str, max_len: int = 1024) -> list[dict]:
    """Add brand name to BODY component if not already present."""
    comps = list(components or [])
    for c in comps:
        if (c.get("type") or "").upper() == "BODY":
            text = c.get("text") or ""
            # Use word boundaries to avoid false positives (e.g., brand in URLs/emails)
            brand_present = re.search(rf"\b{re.escape(brand)}\b", text, flags=re.IGNORECASE) is not None if brand else True
            if brand and not brand_present:
                # append cleanly without breaking placeholders
                sep = " — " if not text.endswith(("!", ".", "…")) else " "
                new = (text + sep + brand).strip()
                c["text"] = new[:max_len]
            return comps
    # No BODY yet → just return; we'll store brand in memory to re-apply later
    return comps

def _shorten_text(text: str, target: int = 140) -> str:
    """Intelligently shorten text to target length."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t) <= target: return t
    sentences = re.split(r"(?<=[.!?])\s+", t)
    acc = ""
    for s in sentences:
        if len(acc) + len(s) + (1 if acc else 0) <= target:
            acc = (acc + " " + s).strip()
        else:
            break
    if acc: return acc
    cut = t[:target].rsplit(" ", 1)[0]
    return (cut + "…") if cut else t[:target]

def _parse_user_directives(cfg: Dict[str,Any], text: str) -> list[dict]:
    """Parse user text and return normalized directives."""
    toks = _tokenize(text)
    text_lower = text.lower()
    s_add, s_btn, s_url, s_phone = _syn(cfg,"add"), _syn(cfg,"button"), _syn(cfg,"url"), _syn(cfg,"phone")
    s_brand, s_shorten = _syn(cfg,"brand"), _syn(cfg,"shorten")
    s_header, s_footer, s_body, s_name = _syn(cfg,"header"), _syn(cfg,"footer"), _syn(cfg,"body"), _syn(cfg,"name")

    directives: list[dict] = []

    # Buttons (improved detection with multiple patterns)
    button_indicators = (
        any(w in toks for w in s_btn) or 
        any(w in toks for w in s_add) and any(btn in text_lower for btn in ["button", "buttons", "cta", "action"]) or
        any(phrase in text_lower for phrase in ["quick repl", "call-to-action", "reply option"]) or
        re.search(r"\bcall\s+us\b", text_lower)  # "call us" patterns
    )
    
    if button_indicators:
        url = URL_RE.search(text)
        phone = PHONE_RE.search(text)
        
        # Enhanced phone detection for "call us" patterns
        if not phone and re.search(r"\bcall\s+us\b", text_lower):
            # Look for phone numbers in context
            phone_patterns = [
                r"call\s+us\s+(?:at\s+)?(\+?[\d\-\s().]{10,})",
                r"(\+?[\d\-\s().]{10,})",  # Any phone-like number
            ]
            for pattern in phone_patterns:
                match = re.search(pattern, text, re.I)
                if match:
                    phone = match
                    break
        
        count = _extract_int(text) or 0
        kind = "quick" if not url and not phone else ("url" if url else "phone")
        
        # Extract phone number correctly
        phone_num = None
        if phone:
            if hasattr(phone, 'groups') and phone.groups():
                phone_num = phone.group(1) if len(phone.groups()) >= 1 else phone.group(0)
            else:
                phone_num = phone.group(0)
        
        directives.append({"type":"add_buttons","kind":kind,"url": url.group(0) if url else None,
                           "phone": phone_num, "count": count})

    # Brand / company name (improved detection)
    brand_indicators = (
        any(w in toks for w in s_brand) or
        any(phrase in text_lower for phrase in ["company name", "brand name", "organization"]) or
        re.search(r"\b(?:company|brand|name)\b", text_lower)
    )
    
    if brand_indicators:
        brand = _extract_brand_name(text)
        if brand:
            directives.append({"type":"set_brand","name":brand})

    # Shorten (optionally with target) - improved multi-intent detection
    shorten_indicators = (
        any(w in toks for w in s_shorten) or
        any(phrase in text_lower for phrase in ["make it short", "make it shorter", "condense", "trim", "reduce length", "shorter"]) or
        re.search(r"\bmake\s+it\s+short", text_lower)
    )
    
    if shorten_indicators:
        target = _extract_int(text) or (((cfg.get("components") or {}).get("text") or {}).get("shorten", {}).get("target_length", 140))
        directives.append({"type":"shorten","target": int(target)})

    # Header / Footer / Body / Name (generic setters if user pasted exact copy)
    if any(w in toks for w in s_name):
        m = re.search(r'name\s*(?:is|=|as)?\s*[""]?([a-z0-9_]{1,64})[""]?', text, re.I)
        if m: directives.append({"type":"set_name","name":m.group(1)})
    if any(w in toks for w in s_body):
        m = re.search(r'(?:body|message|text|content)\s*(?:is|=|:)\s*[""](.+?)[""]', text, re.I|re.S)
        if m: directives.append({"type":"set_body","text":m.group(1).strip()})
    if any(w in toks for w in s_header):
        # accept "header: XXX" → TEXT header
        m = re.search(r'header\s*(?:is|=|:)\s*[""](.+?)[""]', text, re.I|re.S)
        if m: directives.append({"type":"set_header","format":"TEXT","text":m.group(1).strip()})
    if any(w in toks for w in s_footer):
        m = re.search(r'footer\s*(?:is|=|:)\s*[""](.+?)[""]', text, re.I|re.S)
        if m: directives.append({"type":"set_footer","text":m.group(1).strip()})

    return directives

def _apply_directives(cfg: Dict[str,Any], directives: list[dict], candidate: Dict[str,Any], memory: Dict[str,Any]) -> tuple[Dict[str,Any], list[str]]:
    """Apply normalized directives in a category-safe, schema-safe way."""
    out = dict(candidate or {})
    comps = list(out.get("components") or [])
    cat  = (out.get("category") or memory.get("category") or "").upper()
    msgs: list[str] = []

    def _ensure_buttons():
        return next((c for c in comps if (c.get("type") or "").upper()=="BUTTONS"), None)

    for d in directives:
        t = d.get("type")

        # 1) add_buttons
        if t == "add_buttons":
            if cat == "AUTHENTICATION":
                msgs.append("Buttons aren't allowed for AUTH templates; skipped.")
                continue
            btn_block = _ensure_buttons()
            if not btn_block:
                btn_block = {"type":"BUTTONS","buttons":[]}
                comps.append(btn_block)
            buttons = btn_block["buttons"]

            kind = d.get("kind")
            count = max(1, min(3, int(d.get("count") or 0))) if kind == "quick" else 1

            if kind == "url":
                url = d.get("url")
                if url:
                    button_text = "Visit Website"[:20]
                    buttons.append({"type":"URL","text":button_text,"url":url})
                    msgs.append(f"Added URL button ({button_text}).")
                else:
                    msgs.append("Couldn't find a URL; added quick replies instead.")
                    fallback_qrs = _default_quick_replies(cfg, cat)
                    # Don't exceed MAX_BUTTONS when adding fallback buttons
                    existing = len(buttons)
                    space = max(0, MAX_BUTTONS - existing)
                    fallback_qrs = fallback_qrs[:space] if space else []
                    if fallback_qrs:
                        buttons.extend(fallback_qrs)
                    if fallback_qrs:
                        button_labels = [btn.get("text", "") for btn in fallback_qrs[:MAX_BUTTONS]]
                        labels_str = " / ".join(button_labels)
                        msgs.append(f"Added {len(fallback_qrs)} quick replies ({labels_str}).")
            elif kind == "phone":
                phone = d.get("phone")
                if phone:
                    button_text = "Call Us"[:20]
                    normalized_phone = _normalize_phone(phone)
                    buttons.append({"type":"PHONE_NUMBER","text":button_text,"phone_number":normalized_phone})
                    msgs.append(f"Added phone button ({button_text}).")
                else:
                    msgs.append("Couldn't find a phone number; added quick replies instead.")
                    fallback_qrs = _default_quick_replies(cfg, cat)
                    # Don't exceed MAX_BUTTONS when adding fallback buttons  
                    existing = len(buttons)
                    space = max(0, MAX_BUTTONS - existing)
                    fallback_qrs = fallback_qrs[:space] if space else []
                    if fallback_qrs:
                        buttons.extend(fallback_qrs)
                    if fallback_qrs:
                        button_labels = [btn.get("text", "") for btn in fallback_qrs[:MAX_BUTTONS]]
                        labels_str = " / ".join(button_labels)
                        msgs.append(f"Added {len(fallback_qrs)} quick replies ({labels_str}).")
            else:
                # Get business context for smart button generation
                brand = memory.get("brand_name", "")
                business_context = memory.get("business_context", "")
                qrs = _default_quick_replies(cfg, cat, brand, business_context)
                if count and count < len(qrs): qrs = qrs[:count]
                if qrs:
                    # Don't exceed MAX_BUTTONS when adding contextual quick replies
                    existing = len(buttons)
                    space = max(0, MAX_BUTTONS - existing)
                    qrs = qrs[:space] if space else []
                    if qrs:
                        # Enforce button text length limit before adding
                        for q in qrs:
                            q["text"] = str(q.get("text","")).strip()[:20]
                        buttons.extend(qrs)
                    # Create confirmation with actual button labels (up to MAX_BUTTONS) from all buttons in this component
                    all_button_labels = [btn.get("text", "") for btn in buttons[:MAX_BUTTONS]]
                    if len(all_button_labels) <= MAX_BUTTONS:
                        labels_str = " / ".join(all_button_labels)
                        msgs.append(f"Added {len(buttons)} quick replies ({labels_str}).")
                    else:
                        labels_str = " / ".join(all_button_labels[:MAX_BUTTONS])
                        msgs.append(f"Added {len(buttons)} quick replies ({labels_str} + {len(buttons)-MAX_BUTTONS} more).")
                else:
                    # Fallback if no defaults configured
                    fallback_buttons = [{"type":"QUICK_REPLY","text":"Learn More"}, {"type":"QUICK_REPLY","text":"Contact Us"}]
                    # Don't exceed MAX_BUTTONS when adding fallback buttons
                    existing = len(buttons)
                    space = max(0, MAX_BUTTONS - existing)
                    fallback_buttons = fallback_buttons[:space] if space else []
                    if fallback_buttons:
                        buttons.extend(fallback_buttons)
                    # Create confirmation with actual fallback button labels from all buttons
                    all_button_labels = [btn.get("text", "") for btn in buttons[:MAX_BUTTONS]]
                    labels_str = " / ".join(all_button_labels)
                    msgs.append(f"Added {len(buttons)} quick replies ({labels_str}).")
            
            # Deduplicate and cap buttons after adding them
            if buttons:
                buttons = _cap_buttons(buttons)
                # Update the component with processed buttons
                btn_block = _ensure_buttons()
                if btn_block:
                    btn_block["buttons"] = buttons
            
            out["components"] = comps

        # 2) set_brand
        elif t == "set_brand":
            brand = (d.get("name") or "").strip()
            if not brand: continue
            memory["brand_name"] = brand
            new_comps = _ensure_brand_in_body(comps, brand)
            if new_comps is comps:
                # BODY missing → defer
                memory["brand_name_pending"] = brand
                msgs.append(f"Stored brand \"{brand}\"; will add when BODY is present.")
            else:
                comps = new_comps
                msgs.append(f'Added company name "{brand}" to BODY.')
            out["components"] = comps

        # 3) shorten
        elif t == "shorten":
            target = int(d.get("target") or ((cfg.get("components") or {}).get("text") or {}).get("shorten", {}).get("target_length", 140))
            for c in comps:
                if (c.get("type") or "").upper() == "BODY" and (c.get("text") or "").strip():
                    c["text"] = _shorten_text(c["text"], target)
                    msgs.append(f"Shortened BODY to ≈{target} chars.")
                    break
            out["components"] = comps

        # 4) set_name
        elif t == "set_name":
            out["name"] = _slug(d.get("name"))

        # 5) set_body
        elif t == "set_body":
            txt = (d.get("text") or "").strip()
            if txt:
                # Insert/replace first BODY
                replaced = False
                for c in comps:
                    if (c.get("type") or "").upper() == "BODY":
                        c["text"] = txt
                        replaced = True
                        break
                if not replaced:
                    comps.insert(0, {"type":"BODY","text":txt})
                # If brand was pending, inject now
                if memory.get("brand_name_pending"):
                    comps = _ensure_brand_in_body(comps, memory.pop("brand_name_pending"))
                out["components"] = comps
                msgs.append("Updated BODY.")

        # 6) set_header
        elif t == "set_header":
            fmt = (d.get("format") or "TEXT").upper()
            if cat == "AUTHENTICATION" and fmt != "TEXT":
                msgs.append("For AUTH, only TEXT header is allowed; skipped non-TEXT header.")
                continue
            # remove any existing header (only 0–1 allowed)
            comps = [c for c in comps if (c.get("type") or "").upper() != "HEADER"]
            h = {"type":"HEADER","format":fmt}
            if fmt == "TEXT":
                txt = (d.get("text") or "").strip()
                if txt: h["text"] = txt[:60]
            out["components"] = [h] + comps
            msgs.append("Updated HEADER.")

        # 7) set_footer
        elif t == "set_footer":
            txt = (d.get("text") or "").strip()
            # replace or append
            seen = False
            for c in comps:
                if (c.get("type") or "").upper() == "FOOTER":
                    c["text"] = txt[:60]
                    seen = True
                    break
            if not seen: comps.append({"type":"FOOTER","text":txt[:60]})
            out["components"] = comps
            msgs.append("Updated FOOTER.")

    return out, msgs

# --- End of directive parsing engine ---

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
                    item = {"type": "HEADER", "format": "TEXT", "text": txt}
                    # Preserve example for TEXT headers with variables
                    if "example" in comp:
                        item["example"] = comp["example"]
                    clean.append(item)
                elif fmt in {"IMAGE", "VIDEO", "DOCUMENT", "LOCATION"}:
                    item = {"type": "HEADER", "format": fmt}
                    # Always preserve example for media headers (required for most, optional for LOCATION)
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
                        btn_text = (b.get("text") or b.get("label") or b.get("title") or "")[:20]
                        btn_type = b.get("type", "QUICK_REPLY")
                        
                        if not btn_text.strip():
                            continue
                        
                        # Normalize invalid button types to valid WhatsApp API types
                        if btn_type.lower() in ("reply", "button"):
                            btn_type = "QUICK_REPLY"
                        elif btn_type.upper() not in ("QUICK_REPLY", "URL", "PHONE_NUMBER"):
                            btn_type = "QUICK_REPLY"  # Default fallback
                            
                        # Normalize button structure + enforce label length
                        btn = {"type": btn_type, "text": str(btn_text).strip()[:20]}
                        
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
                            btn["phone_number"] = _normalize_phone(phone)
                            
                        b2.append(btn)
                    # Enforce WhatsApp limit at sanitize time too
                    if b2:
                        clean.append({"type":"BUTTONS","buttons": b2[:MAX_BUTTONS]})
                elif comp.get("text") or comp.get("label") or comp.get("title"):
                    # Malformed format: Individual BUTTONS component with text/label/title
                    # Collect these to convert to proper format
                    btn_text = (comp.get("text") or comp.get("label") or comp.get("title") or "").strip()[:20]
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
            clean.append({"type": "BUTTONS", "buttons": collected_buttons[:MAX_BUTTONS]})
                        
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
    
    # HANDLE ROOT-LEVEL BUTTONS: Convert to proper BUTTONS component or remove duplicates
    if "buttons" in c and c["buttons"]:
        components = c.get("components", [])
        
        # Check if we already have a BUTTONS component
        has_button_component = any(
            isinstance(comp, dict) and comp.get("type") == "BUTTONS"
            for comp in components
        )
        
        if has_button_component:
            # Remove root-level buttons to prevent duplication
            c.pop("buttons", None)
        else:
            # Convert root-level buttons to proper BUTTONS component
            root_buttons = c.pop("buttons")
            
            # Normalize button structure for components
            normalized_buttons = []
            for btn in root_buttons:
                if isinstance(btn, dict):
                    # Handle different button formats from LLM
                    if btn.get("type") == "reply" and btn.get("reply"):
                        # Convert reply format to standard format
                        reply = btn["reply"]
                        normalized_btn = {
                            "type": "QUICK_REPLY",
                            "text": reply.get("title") or reply.get("text", "Button")
                        }
                        if reply.get("id"):
                            normalized_btn["payload"] = reply["id"]
                        normalized_buttons.append(normalized_btn)
                    else:
                        # Standard format or other types - try multiple text fields
                        btn_text = (btn.get("text") or btn.get("title") or btn.get("label") or 
                                   btn.get("value") or "Button")[:20]
                        btn_type = btn.get("type", "QUICK_REPLY")
                        
                        # Normalize invalid button types to valid WhatsApp API types
                        if btn_type.lower() in ("reply", "button"):
                            btn_type = "QUICK_REPLY"
                        elif btn_type.upper() not in ("QUICK_REPLY", "URL", "PHONE_NUMBER"):
                            btn_type = "QUICK_REPLY"  # Default fallback
                        
                        normalized_btn = {"type": btn_type, "text": btn_text}
                        
                        # Preserve additional fields
                        if btn.get("payload"):
                            normalized_btn["payload"] = btn["payload"]
                        if btn.get("url"):
                            normalized_btn["url"] = btn["url"]
                        if btn.get("phone_number"):
                            normalized_btn["phone_number"] = _normalize_phone(btn["phone_number"])
                            
                        normalized_buttons.append(normalized_btn)
            
            # Add BUTTONS component
            if normalized_buttons:
                # Enforce label length + max count at conversion point too
                for nb in normalized_buttons:
                    if "text" in nb:
                        nb["text"] = str(nb["text"]).strip()[:20]
                components.append({"type": "BUTTONS", "buttons": normalized_buttons[:MAX_BUTTONS]})
                c["components"] = components
    
    # Apply AUTH category constraints and button normalization
    cat = (c.get("category") or "").upper()
    if cat == "AUTHENTICATION":
        # Remove buttons (not allowed for AUTH)
        components = c.get("components", [])
        components = [comp for comp in components if not (isinstance(comp, dict) and (comp.get("type") or "").upper() == "BUTTONS")]
        
        # Enforce TEXT-only headers for AUTHENTICATION
        for comp in components:
            if isinstance(comp, dict) and (comp.get("type") or "").upper() == "HEADER":
                comp["format"] = "TEXT"
                comp.pop("example", None)  # Remove examples for TEXT headers unless needed for variables
        
        c["components"] = components
    
    # Apply button capping and deduplication everywhere
    components = c.get("components", [])
    for comp in components:
        if isinstance(comp, dict) and (comp.get("type") or "").upper() == "BUTTONS":
            buttons = comp.get("buttons", [])
            if buttons:
                comp["buttons"] = _cap_buttons(buttons)
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
    
    if cat == "AUTHENTICATION":
        # For AUTH, only allow TEXT header if explicitly requested
        if memory.get("wants_header") and not _has_component(p, "HEADER"):
            miss.append("header")
    elif not skip_extras:
        # For non-AUTH categories, allow all extras if not skipped
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

    def has(kind: str) -> bool:
        return any(isinstance(c, dict) and (c.get("type") or "").upper() == kind for c in comps)

    changed = False
    cat = (memory.get("category") or cand.get("category") or "").upper()
    
    # For AUTHENTICATION category, allow TEXT header if user specifically requests it
    if memory.get("wants_header") and not has("HEADER"):
        if cat == "AUTHENTICATION":
            # Only add TEXT header for AUTHENTICATION category
            hdr = (memory.get("event_label") or "Authentication code")[:60]
            comps.insert(0, {"type": "HEADER", "format": "TEXT", "text": hdr})
            changed = True
        elif cat != "AUTHENTICATION":
            # For non-AUTH categories, use default behavior
            hdr = (memory.get("event_label") or "Special offer just for you!")[:60]
            comps.insert(0, {"type": "HEADER", "format": "TEXT", "text": hdr})
            changed = True
    
    # Block footer and buttons for AUTHENTICATION
    if cat != "AUTHENTICATION":
        if memory.get("wants_footer") and not has("FOOTER"):
            comps.append({"type":"FOOTER","text":"Thank you!"})
            changed = True
        if memory.get("wants_buttons") and not has("BUTTONS"):
            # Use configuration-driven defaults with business context
            cfg = get_config() or {}
            brand = memory.get("brand_name", "")
            business_context = memory.get("business_type", "")
            buttons = _default_quick_replies(cfg, cat, brand, business_context)
            if buttons:
                buttons = _cap_buttons(buttons)  # Apply capping and deduplication
                comps.append({
                    "type":"BUTTONS",
                    "buttons": buttons
                })
                changed = True
        elif memory.get("wants_buttons") and has("BUTTONS"):
            # Handle adding more buttons - use centralized capping
            existing_comp = next((c for c in comps if c.get("type") == "BUTTONS"), None)
            if existing_comp:
                existing_buttons = existing_comp.get("buttons", [])
                
                # Generate new buttons and merge
                cfg = get_config() or {}
                brand = memory.get("brand_name", "")
                business_context = memory.get("business_type", "")
                new_buttons = _default_quick_replies(cfg, cat, brand, business_context)
                
                # Combine and apply centralized capping/deduplication
                all_buttons = existing_buttons + new_buttons
                existing_comp["buttons"] = _cap_buttons(all_buttons)
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
        # Generate dynamic examples based on context
        example_labels = ["View offers", "Order now", "Learn more", "Call us", "Visit store", "Get quote"]
        selected = example_labels[:2]  # Take first 2
        return f"You asked for buttons. Should I add two quick replies like '{selected[0]}' and '{selected[1]}'?"
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
    
    # 2) Load user business profile for better context
    business_profile = None
    if inp.user_id:
        business_profile = await get_user_business_profile(db, inp.user_id)
    
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

    # Pre-populate memory from business profile if available and not already set
    if business_profile:
        if not memory.get("business_name") and business_profile.business_name:
            memory["business_name"] = business_profile.business_name
        if not memory.get("business_type") and business_profile.business_type:
            memory["business_type"] = business_profile.business_type
        if not memory.get("brand_name") and business_profile.business_name:
            memory["brand_name"] = business_profile.business_name
        if not memory.get("industry") and business_profile.industry:
            memory["industry"] = business_profile.industry
        if not memory.get("category") and business_profile.default_category:
            memory["category"] = business_profile.default_category
        if not memory.get("language_pref") and business_profile.default_language:
            memory["language_pref"] = business_profile.default_language

    # 2) Build LLM inputs + call
    # Use comprehensive system prompt for better user experience
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
    
    # Auto-detect category from promotional intent
    if not memory.get("category") and not draft.get("category"):
        promo_keywords = ["promotional", "promotion", "offer", "discount", "sale", "special", "deal"]
        if any(keyword in safe_message.lower() for keyword in promo_keywords):
            memory["category"] = "MARKETING"
            draft["category"] = "MARKETING"
    
    # Auto-detect category from authentication intent
    if not memory.get("category") and not draft.get("category"):
        auth_keywords = ["login", "password", "code", "verification", "otp", "security", "verify", "authenticate", "pin", "token"]
        if any(keyword in safe_message.lower() for keyword in auth_keywords):
            memory["category"] = "AUTHENTICATION"
            draft["category"] = "AUTHENTICATION"
    
    # Extract business context more broadly
    if not memory.get("business_type"):
        business_type = _detect_business_type(safe_message, memory.get("brand_name", ""))
        if business_type != "general":
            memory["business_type"] = business_type
    
    # Extract brand name if mentioned - improved pattern
    if not memory.get("brand_name"):
        brand_patterns = [
            r'(?:shop|store|business|company|clinic|salon)\s+(?:called|named)\s+([A-Z][A-Za-z\s]+)',
            r'(?:called|named)\s+([A-Z][A-Za-z\s]+)(?:\s+(?:shop|store|business|company))?',
            r'my\s+(?:shop|store|business|company)\s+([A-Z][A-Za-z\s]+)',
            r'([A-Z][A-Za-z\s]+)\s+(?:shop|store|business|company)',
            r'at\s+([A-Z][A-Za-z\s]+)(?:\s+(?:shop|store))?'
        ]
        
        for pattern in brand_patterns:
            match = re.search(pattern, safe_message)
            if match:
                potential_brand = match.group(1).strip()
                if len(potential_brand) > 2 and potential_brand not in ['Sweet', 'Shop', 'Store']:
                    memory["brand_name"] = potential_brand
                    break

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
        
        # Directly inject content into draft if we found it
        components = draft.get("components", [])
        body_comp = next((c for c in components if c.get("type") == "BODY"), None)
        if not body_comp or not body_comp.get("text", "").strip():
            # Create or update body component
            if body_comp:
                body_comp["text"] = explicit_content
            else:
                components.append({"type": "BODY", "text": explicit_content})
            draft["components"] = components
            d.draft = draft
    
    s.memory = memory

    # Inject business context into LLM memory for better button generation
    if memory.get("business_type") and memory.get("business_type") != "general":
        memory["llm_context_hint"] = f"Business: {memory.get('business_type', 'general')} {memory.get('brand_name', '')}"
    
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
    
    # Ensure candidate is always a dictionary
    if not isinstance(candidate, dict):
        candidate = {}
    
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

        # Parse and apply robust directives from user text (multi-intent, config-driven)
        directives = _parse_user_directives(cfg, safe_message)
        msgs_applied = []
        if directives:
            merged2, msgs_applied = _apply_directives(cfg, directives, merged, memory)
            if merged2 != merged:
                merged = merged2
                d.draft = merged
                # refresh memory if brand pending was set
                s.memory = memory

        # Apply AUTHENTICATION category constraints - remove buttons if category is AUTH
        cat = (merged.get("category") or memory.get("category") or "").upper()
        if cat == "AUTHENTICATION":
            components = merged.get("components", [])
           
            original_length = len(components)
            filtered_components = [comp for comp in components if not (isinstance(comp, dict) and (comp.get("type") or "").upper() == "BUTTONS")]
            if len(filtered_components) < original_length:
                merged["components"] = filtered_components
                d.draft = merged
                # Clear any button-related memory flags
                memory.pop("wants_buttons", None)
                s.memory = memory
                msgs_applied = (msgs_applied or []) + ["Removed buttons (not allowed for Authentication templates)."]

        # If brand was pending and BODY appeared via LLM later, inject it automatically
        if memory.get("brand_name_pending"):
            has_body = any((c.get("type") or "").upper()=="BODY" for c in (merged.get("components") or []))
            if has_body:
                merged["components"] = _ensure_brand_in_body(merged.get("components") or [], memory.pop("brand_name_pending"))
                d.draft = merged
                s.memory = memory
                msgs_applied = (msgs_applied or []) + ["Added stored brand to BODY."]

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
        
        # Force completion if all required fields are actually present
        if not computed_missing:
            missing = []
            # Create a clean final payload
            final_payload = {
                "name": merged.get("name"),
                "category": merged.get("category"), 
                "language": merged.get("language"),
                "components": merged.get("components", [])
            }
            
            # Check if we actually have all required content
            has_all_required = (
                final_payload.get("name") and 
                final_payload.get("category") and 
                final_payload.get("language") and
                any(isinstance(c, dict) and (c.get("type") or "").upper() == "BODY" and (c.get("text") or "").strip()
                    for c in final_payload.get("components", []))
            )
            
            if has_all_required:
                # Override LLM action and force immediate completion
                out["agent_action"] = "FINAL"
                out["final_creation_payload"] = final_payload
                out["message_to_user"] = "Perfect! 🎉 Your template is complete and ready to use!"
                out["missing"] = []
                action = "FINAL"
                
                # Save business profile and complete immediately
                await _save_business_profile_if_present(db, inp.user_id, memory)
                
                # Skip all validation and go straight to completion
                d.finalized_payload = final_payload
                d.status = "FINAL"
                d.draft = merged
                s.last_action = "FINAL"
                s.data = {**(s.data or {}), "messages": _append_history(inp.message, s.data.get("messages", [-1]).get("content", ""), out["message_to_user"])}
                await touch_user_session(db, inp.user_id, s.id)
                await upsert_session(db, s); await db.commit()
                
                return ChatResponse(
                    session_id=s.id, 
                    reply=out["message_to_user"], 
                    draft=merged,
                    missing=[], 
                    final_creation_payload=final_payload
                )

        # Mark success in memory after applying extras
        if any(extras_present.values()):
            memory = merge_deep(memory, {"extras_choice": "accepted"})
            s.memory = memory

        final_reply = (reply or _targeted_missing_reply(missing, memory)).strip()

        # If we applied deterministic edits and the LLM reply is generic, override with a helpful confirmation
        if (msgs_applied) and (not reply or reply.strip().lower().startswith("please tell me more") or 
                              "what quick reply buttons" in reply.lower() or "what specific buttons" in reply.lower() or
                              "what buttons would you like" in reply.lower()):
            final_reply = "; ".join(msgs_applied) + " Anything else to add?"
        
        # Special handling for button confirmations - prioritize our detailed confirmations
        elif (msgs_applied and any("quick replies" in msg for msg in msgs_applied) and 
              _has_component(merged, "BUTTONS")):
            final_reply = "; ".join(msgs_applied) + " Anything else to add?"

        # Add encouragement and examples from friendly_prompts when appropriate
        if len(msgs) > 0 and any(extras_present.values()):
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

        # Only apply stale overrides if we don't have deterministic messages from directives
        deterministic = bool(msgs_applied)
        
        if not deterministic and _has_component(merged, "BUTTONS") and "button" in final_reply.lower():
            # Build message from actual button texts in the draft
            btn_comp = next((c for c in (merged.get("components") or []) if (c.get("type") or "").upper() == "BUTTONS"), None)
            if btn_comp:
                labels = [b.get("text","").strip() for b in (btn_comp.get("buttons") or []) if b.get("text")]
                shown = ", ".join(labels[:MAX_BUTTONS]) if labels else "your quick replies"
                final_reply = f"Added quick replies ({shown}). Anything else to add?"
            else:
                final_reply = "Added quick reply buttons. Anything else to add?"
        if not deterministic and extras_present["header"] and "header" in final_reply.lower():
            final_reply = "Added a short TEXT header. Anything else to add?"
        if not deterministic and extras_present["footer"] and "footer" in final_reply.lower():
            final_reply = "Added a short footer. Anything else to add?"
        return await _persist_turn_and_return(final_reply, merged, missing)

    # 7) FINAL → sanitize -> validate -> persist (also enforce requested extras)
    if action == "FINAL":
        candidate = _auto_apply_extras_on_yes(safe_message, candidate, memory)
        cand_clean = _sanitize_candidate(candidate) if candidate else {}
        candidate = cand_clean or draft or _minimal_scaffold(memory)

        def _has_component_kind(p: Dict[str, Any], kind: str) -> bool:
            return any(isinstance(c, dict) and (c.get("type") or "").upper() == kind for c in (p.get("components") or []))

        # Pre-FINAL guard: For AUTHENTICATION category, reject non-TEXT headers and remove buttons
        cat = (candidate.get("category") or memory.get("category") or "").upper()
        if cat == "AUTHENTICATION":
            # Check for non-TEXT headers
            for comp in (candidate.get("components") or []):
                if isinstance(comp, dict) and (comp.get("type") or "").upper() == "HEADER":
                    header_format = (comp.get("format") or "").upper()
                    if header_format and header_format != "TEXT":
                        d.draft = merge_deep(draft, candidate)
                        s.last_action = "ASK"
                        error_msg = f"Authentication templates only allow TEXT headers, not {header_format}. Please use a simple text header or remove the header component."
                        s.data = {**(s.data or {}), "messages": _append_history(inp.message, error_msg)}
                        await touch_user_session(db, inp.user_id, s.id)
                        await upsert_session(db, s); await db.commit()
                        return ChatResponse(session_id=s.id, reply=error_msg, draft=d.draft,
                                            missing=_compute_missing(d.draft, memory),
                                            final_creation_payload=None)
            
            # Remove any buttons - AUTHENTICATION templates cannot have interactive elements
            components = candidate.get("components", [])
            filtered_components = [comp for comp in components if not (isinstance(comp, dict) and (comp.get("type") or "").upper() == "BUTTONS")]
            if len(filtered_components) < len(components):
                candidate["components"] = filtered_components
                # Clear any button-related memory flags
                memory.pop("wants_buttons", None)
                s.memory = memory

        # enforce requested extras before validate (only for non-AUTH categories)
        missing_extras = []
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
        
        # Save business profile on successful completion
        await _save_business_profile_if_present(db, inp.user_id, memory)
        
        return ChatResponse(session_id=s.id, reply=reply or "Finalized.", draft=d.draft,
                            missing=[], final_creation_payload=candidate_for_validation)

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
    
    # Save business profile if we have business context
    await _save_business_profile_if_present(db, inp.user_id, memory)
    
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

def _extract_explicit_content(message: str) -> str:
    """Extract explicit content from user message."""
    patterns = [
        # Direct content patterns
        r"(?:message should say|text should be|content is|message is|should say|wants to say):\s*[\"']?(.+?)[\"']?(?:\s*$|\.|!|\?)",
        r"(?:create a message|template).*?(?:saying|that says|with text):\s*[\"']?(.+?)[\"']?(?:\s*$|\.|!|\?)",
        r"(?:send|create).*?[\"'](.{15,})[\"']",  # Quoted content (min 15 chars)
        
        # Promotional content patterns
        r"(?:special|offer|discount|promotion|sale).*?[\"']?([^\"']{20,})[\"']?(?:\s*$|\.|!|\?)",
        r"(?:get|enjoy|grab|buy).*?(\d+%?\s*off.*?)(?:\.|!|$)",
        
        # Message-like patterns
        r"^[\"']?([A-Z][^\"']{20,})[\"']?[.!]?\s*$",  # Standalone sentences starting with capital
        r"(?:message|text).*?[\"']([^\"']{15,})[\"']",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE | re.DOTALL)
        if match:
            content = match.group(1).strip()
            # Clean up common artifacts
            content = re.sub(r'\s+', ' ', content)  # Normalize whitespace
            content = content.strip('.,;:!?')  # Remove trailing punctuation
            
            if len(content) >= 10 and not content.lower().startswith(('http', 'www')):
                return content
    
    return ""

def _get_journey_stage_from_memory(memory: Dict[str, Any]) -> str:
    """Determine conversation journey stage from memory."""
    if not memory.get("category"):
        return "welcome"
    elif not memory.get("business_type") and not memory.get("brand_name"):
        return "business_context"
    elif not any(memory.get(k) for k in ["body", "content"]):
        return "content_creation"
    elif memory.get("wants_buttons") or memory.get("wants_header") or memory.get("wants_footer"):
        return "add_extras"
    else:
        return "review"


async def _save_business_profile_if_present(db: AsyncSession, user_id: str, memory: Dict[str, Any]):
    """Helper to save business profile from memory if present."""
    if not user_id or not memory:
        return
        
    try:
        business_data = {}
        
        # Extract business information from memory
        if memory.get("business_name"):
            business_data["business_name"] = memory["business_name"]
        if memory.get("business_type"):
            business_data["business_type"] = memory["business_type"]
        if memory.get("brand_name"):
            business_data["brand_name"] = memory["brand_name"]
        if memory.get("industry"):
            business_data["industry"] = memory["industry"]
        if memory.get("category"):
            business_data["category"] = memory["category"]
        if memory.get("language_pref"):
            business_data["language_preference"] = memory["language_pref"]
        if memory.get("phone_number"):
            business_data["phone_number"] = _normalize_phone(memory["phone_number"])
        
        # Save to business profile if we have meaningful data
        if business_data:
            await upsert_user_business_profile(db, user_id, business_data)
    except Exception as e:
        # Don't fail the chat if business profile saving fails
        print(f"Warning: Could not save business profile: {e}")

def _normalize_phone(phone_number: str) -> str:
    """Normalize phone number by stripping whitespace and common formatting characters."""
    if not phone_number:
        return phone_number
    return phone_number.replace(" ", "").replace("-", "").replace("(", "").replace(")", "").replace(".", "").strip()


