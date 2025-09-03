from __future__ import annotations
from typing import Dict, Any, List, Tuple
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.engine.url import make_url
import os
import re
import datetime as dt
import hashlib
import copy

from .db import engine, SessionLocal, Base
from .models import Draft, User, UserSession
from .repo import (
    get_or_create_session,
    upsert_session,
    create_draft,
    log_llm,
    upsert_user_session,
    touch_user_session,
)
from .config import get_config, get_cors_origins, is_production
from .prompts import build_context_block, build_friendly_system_prompt
from .llm import LlmClient
from .validator import validate_schema, lint_rules
from .schemas import ChatInput, ChatResponse, SessionData, ChatMessage
from .utils import merge_deep, scrub_sensitive_data

# Optional interactive router
try:
    from .interactive import router as interactive_router
except Exception as _e:
    interactive_router = None

# --------------------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------------------
app = FastAPI(title="LLM-First WhatsApp Template Builder", version="4.1.0")

from .routes import config as routes_config, debug, users, sessions
app.include_router(routes_config.router)
app.include_router(debug.router)
app.include_router(users.router)
app.include_router(sessions.router)
if interactive_router is not None:
    app.include_router(interactive_router)

# --------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------

def _qhash(s: str) -> str:
    return hashlib.sha1((s or "").encode("utf-8")).hexdigest()[:12]


def _redact_secrets(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Redact potentially sensitive information from log payloads (IDs hashed)."""
    if not isinstance(payload, dict):
        return payload

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
                if any(hk in kl for hk in hash_keys):
                    out[k] = f"[HASH:{_hash(v)}]"; continue
                if any(sens in kl for sens in sensitive_keys):
                    out[k] = "[REDACTED]"; continue
                if k in preserve_keys:
                    out[k] = walk(v, preserve_strings=True); continue
                out[k] = walk(v, preserve_strings=False)
            return out
        if isinstance(obj, list):
            return [walk(x, preserve_strings) for x in obj]
        if isinstance(obj, str):
            if preserve_strings:
                return obj
            return obj if len(obj) <= 200 else obj[:100] + "...[TRUNCATED]"
        return obj

    return walk(copy.deepcopy(payload))


# --------------------------------------------------------------------------------------
# Startup / DB
# --------------------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

async def get_db() -> AsyncSession:
    async with SessionLocal() as s:
        yield s


@app.on_event("startup")
async def on_startup():
    try:
        safe = make_url(os.getenv("DATABASE_URL", "")).set(password="***")
        print(f"[DEBUG] FastAPI startup: DATABASE_URL={safe}")
    except Exception:
        pass

    async with engine.begin() as aconn:
        await aconn.run_sync(Base.metadata.create_all)

    try:
        if engine.url.drivername.startswith("sqlite"):
            if is_production():
                print("[WARNING] Using SQLite in production. Prefer PostgreSQL.")
            async with engine.begin() as aconn:
                await aconn.exec_driver_sql("PRAGMA journal_mode=WAL;")
                await aconn.exec_driver_sql("PRAGMA synchronous=NORMAL;")
                await aconn.exec_driver_sql("PRAGMA foreign_keys=ON;")
    except Exception:
        pass

# --------------------------------------------------------------------------------------
# Normalization / NLP helpers
# --------------------------------------------------------------------------------------
LANG_MAP = {
    "english": "en_US", "en": "en_US", "en_us": "en_US", "english_us": "en_US",
    "hindi": "hi_IN", "hi": "hi_IN", "hi_in": "hi_IN", "hindi_in": "hi_IN",
    "spanish": "es_MX", "es": "es_MX", "es_mx": "es_MX", "spanish_mx": "es_MX",
}

AFFIRM_REGEX = re.compile(
    r"^\s*(yes|y|ok|okay|sure|sounds\s+good|go\s+ahead|please\s+proceed|proceed|confirm|finalize|do\s+it)\b",
    re.I,
)

URL_RE   = re.compile(r"(https?://[^\s]+)", re.I)
PHONE_RE = re.compile(r"(\+?[\d\-\s().]{10,})", re.I)


def _normalize_language(s: str | None) -> str | None:
    if not s:
        return None
    key = re.sub(r"[^a-z_]", "", s.strip().lower().replace("-", "_").replace(" ", "_"))
    return LANG_MAP.get(key, s if "_" in s else None)


def _is_affirmation(text: str) -> bool:
    return bool(AFFIRM_REGEX.match(text or ""))


def _sanitize_user_input(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = text.strip()
    if len(text) > 2000:
        text = text[:2000]
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


def _slug(s_: str) -> str:
    s_ = (s_ or "").lower().strip()
    s_ = re.sub(r"[^a-z0-9_]+", "_", s_)
    return (re.sub(r"_+", "_", s_).strip("_") or "template")[:64]


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_+:/.-]+", (text or "").lower())


def _get_cfg_tone(cfg: Dict[str, Any]) -> str:
    # "concise" or "friendly" (default to concise for production)
    return (((cfg.get("ux") or {}).get("tone") or (cfg.get("responses") or {}).get("tone") or "concise").lower())


# --------------------------------------------------------------------------------------
# Enhanced button and directive helpers
# --------------------------------------------------------------------------------------

NUM_WORDS = {"one": 1, "two": 2, "three": 3, "1": 1, "2": 2, "3": 3}

def _word_to_int(s: str | None) -> int | None:
    if not s: return None
    s = re.sub(r"[^\w]", "", s.strip().lower())
    return NUM_WORDS.get(s)

def _summarize_buttons_enhanced(btns: list[dict]) -> str:
    labels = [b.get("text", "").strip() for b in (btns or []) if b.get("text")]
    labels = [l for l in labels if l]
    if not labels: return "no buttons"
    if len(labels) == 1: return f"1 quick reply ({labels[0]})"
    return f"{len(labels)} quick replies ({' / '.join(labels[:3])})"

def _cap_buttons_enhanced(buttons: list[dict], cap: int) -> list[dict]:
    # Keep first occurrence per visible text; respect max allowed
    seen = set()
    out = []
    for b in buttons:
        t = (b.get("text") or "").strip()
        if not t or t.lower() in seen:
            continue
        out.append(b)
        seen.add(t.lower())
        if len(out) >= cap:
            break
    return out

def _normalize_phone(raw: str | None) -> str | None:
    if not raw: return None
    digits = re.sub(r"[^\d+]", "", raw)
    # naive gate: 10+ digits
    return digits if len(re.sub(r"\D", "", digits)) >= 10 else None

def _syn(cfg: Dict[str, Any], key: str) -> list[str]:
    """Get synonyms from config for NLP matching"""
    return (((cfg.get("nlp") or {}).get("synonyms") or {}).get(key, [key]))

def _cap_buttons(cfg: Dict[str, Any], n: int) -> int:
    try:
        return max(0, min(int(n), int((((cfg.get("components") or {}).get("buttons") or {}).get("max", 3)))))
    except Exception:
        return max(0, min(int(n), 3))

# --------------------------------------------------------------------------------------
# Business/button intelligence
# --------------------------------------------------------------------------------------

def _detect_business_type(brand: str, context: str) -> str:
    text = f"{brand} {context}".lower()
    if any(word in text for word in ["sweet", "bakery", "cake", "mithai", "dessert", "confection"]):
        return "sweets"
    if any(word in text for word in ["restaurant", "cafe", "food", "kitchen", "dining"]):
        return "restaurant"
    if any(word in text for word in ["clinic", "doctor", "medical", "health", "hospital", "pharmacy"]):
        return "healthcare"
    if any(word in text for word in ["salon", "beauty", "spa", "hair", "nails", "massage"]):
        return "beauty"
    if any(word in text for word in ["shop", "store", "retail", "fashion", "clothes", "boutique"]):
        return "retail"
    if any(word in text for word in ["service", "repair", "maintenance", "cleaning"]):
        return "services"
    return "general"


def _default_quick_replies(cfg: Dict[str, Any], category: str, brand: str = "", business_context: str = "") -> list[dict]:
    cat = (category or "").upper()
    if brand or business_context:
        business_type = _detect_business_type(brand, business_context)
        mapping = {
            "sweets": {"MARKETING": ["Order sweets", "View menu", "Call store"], "UTILITY": ["Track order", "Reorder", "Contact us"]},
            "restaurant": {"MARKETING": ["Book table", "View menu", "Order now"], "UTILITY": ["Confirm booking", "Modify order", "Call restaurant"]},
            "healthcare": {"MARKETING": ["Book appointment", "Learn more", "Contact clinic"], "UTILITY": ["Reschedule", "Confirm", "Call clinic"]},
            "beauty": {"MARKETING": ["Book appointment", "View services", "Special offers"], "UTILITY": ["Reschedule", "Confirm booking", "Contact salon"]},
            "retail": {"MARKETING": ["Shop now", "View catalog", "Get directions"], "UTILITY": ["Track order", "Return item", "Support"]},
            "services": {"MARKETING": ["Get quote", "Schedule visit", "Learn more"], "UTILITY": ["Reschedule", "Confirm service", "Contact us"]},
        }
        labels = (mapping.get(business_type, {}).get(cat) or [])
        if labels:
            return [{"type": "QUICK_REPLY", "text": l[:20]} for l in labels[:3]]
    # fallback to config
    buttons_cfg = (((cfg.get("lint_rules") or {}).get("components") or {}).get("buttons") or {})
    defaults_by_cat = (buttons_cfg.get("defaults_by_category") or {})
    labels = defaults_by_cat.get(cat, defaults_by_cat.get("MARKETING", ["Shop now", "Learn more", "Contact us"]))
    labels = [str(x).strip()[:20] for x in labels if str(x).strip()]
    return [{"type": "QUICK_REPLY", "text": lbl} for lbl in labels[:3]]


# --------------------------------------------------------------------------------------
# Directive parsing
# --------------------------------------------------------------------------------------

def _extract_int(text: str) -> int | None:
    m = re.search(r"\b(\d{1,3})\b", text)
    return int(m.group(1)) if m else None


def _extract_brand_name(text: str) -> str | None:
    patterns = [
        r"\b(?:company|brand)\s+name\s+(?:is|as|=)\s+(?P<brand>.+?)(?:\s+(?:in|for|and|with)\b|$)",
        r"\bmy\s+(?:company|brand)\s+(?:is|as|=)\s+(?P<brand>.+?)(?:\s+(?:in|for|and|with)\b|$)",
        r"\b(?:use|set|add|include)\s+(?P<brand>.+?)\s+as\s+(?:company|brand)\s+name\b",
        r"\b(?:add|include|insert)\s+(?:company|brand)\s+name\s+(?P<brand>.+?)(?:\s+(?:in|for|and|with)\b|$)",
    ]
    txt = (text or "").strip()
    for pat in patterns:
        m = re.search(pat, txt, re.I)
        if m:
            brand = (m.group("brand") or "").strip(' "\'.,;!:' )
            brand = re.split(r"\s+(?:in|for|and|with|to|as)\b", brand)[0].strip()
            if brand and len(brand) > 1 and not re.match(r"^(name|brand|company)$", brand, re.I):
                return brand[:60]
    q = re.search(r'["\'](.+?)["\']', txt)
    if q and len(q.group(1)) > 1:
        return q.group(1)[:60].strip()
    return None


def _shorten_text(text: str, target: int = 140) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t) <= target:
        return t
    sentences = re.split(r"(?<=[.!?])\s+", t)
    acc = ""
    for s in sentences:
        if len(acc) + len(s) + (1 if acc else 0) <= target:
            acc = (acc + " " + s).strip()
        else:
            break
    if acc:
        return acc
    cut = t[:target].rsplit(" ", 1)[0]
    return (cut + "…") if cut else t[:target]


def _ensure_brand_in_body(components: list[dict], brand: str, max_len: int = 1024) -> list[dict]:
    comps = list(components or [])
    for c in comps:
        if (c.get("type") or "").upper() == "BODY":
            text = c.get("text") or ""
            if brand and not re.search(rf"\b{re.escape(brand)}\b", text, flags=re.I):
                sep = " — " if not text.endswith(("!", ".", "…")) else " "
                c["text"] = (text + sep + brand)[:max_len]
            return comps
    return comps


def _parse_user_directives(cfg: Dict[str, Any], text: str) -> list[dict]:
    """Parse user text into normalized directives with strong coverage for buttons, brand, shorten, and set fields."""
    toks = _tokenize(text)
    lower = (text or "").lower()

    s_add = _syn(cfg, "add")
    s_btn = _syn(cfg, "button") 
    s_only = _syn(cfg, "only")
    s_modify = _syn(cfg, "modify")
    s_shorten = _syn(cfg, "shorten")
    s_brand = _syn(cfg, "brand")
    s_header = _syn(cfg, "header")
    s_footer = _syn(cfg, "footer")
    s_body = _syn(cfg, "body")
    s_name = _syn(cfg, "name")

    directives: list[dict] = []

    # ---- BUTTONS (explicit labels & modes) ----
    wants_button = any(w in toks for w in s_btn) or "button" in lower or "buttons" in lower
    intends_modify = any(w in toks for w in s_modify) or "modify" in lower or "change" in lower or "update" in lower
    intends_only = any(w in toks for w in s_only) or "only one" in lower or "single button" in lower or "just one" in lower or "exactly one" in lower

    # capture quoted labels "Get Now", 'Shop now'
    quoted_labels = re.findall(r'["\']([^"\']{1,40})["\']', text)

    # capture raw labels after 'button(s)' or verbs; allow comma-separated
    raw_after = re.search(r'(?:button(?:s)?(?:\s*(?:to|as|named|label(?:ed)?)\s*)?|modify\s*(?:the)?\s*button(?:s)?\s*(?:to)?)[\s:,-]*(.+)$', lower)
    trailing_labels = []
    if raw_after:
        # take non-URL-ish words, strip punctuation, split by comma
        tail = text[raw_after.start(1):].strip()
        parts = [p.strip(" ,.;:") for p in re.split(r",|/| and ", tail) if p.strip()]
        # filter out obvious noise like numbers without words
        trailing_labels = [p for p in parts if not re.match(r"^https?://", p, re.I)]

    # decide count
    num = None
    # words or digits near 'button'
    mnum = re.search(r'(?:(?:only|just|single|exactly)\s+)?(one|two|three|[123])\s+button', lower)
    if mnum:
        num = _word_to_int(mnum.group(1))
    if num is None:
        # fallback: any plain integer anywhere (e.g., "add 1 button")
        mnum2 = re.search(r'\b([123])\b', lower)
        if mnum2: 
            num = _word_to_int(mnum2.group(1))

    # extract URL / phone intent (for URL/PHONE buttons)
    url_match = re.search(r'(https?://[^\s]+)', text, re.I)
    phone_match = re.search(r'(?:call\s+us\s*(?:at)?\s*)?(\+?[\d\-\s().]{10,})', text, re.I)
    phone_norm = _normalize_phone(phone_match.group(1)) if phone_match else None

    if wants_button or intends_modify:
        labels = quoted_labels or trailing_labels
        labels = [re.sub(r"\s+", " ", l).strip() for l in labels]
        labels = [l for l in labels if l and len(l) <= 25]  # WA 25-char guard

        # default kind
        kind = "quick"
        if url_match:
            kind = "url"
        elif phone_norm:
            kind = "phone"

        # explicit modify/replace case
        if intends_modify or intends_only:
            directives.append({
                "type": "set_buttons",     # replace exact
                "kind": kind,
                "labels": labels[:3] if labels else None,
                "url": url_match.group(1) if url_match else None,
                "phone": phone_norm,
                "count": num or (1 if intends_only else None)
            })
        else:
            # additive (still bounded/capped later)
            directives.append({
                "type": "add_buttons",
                "kind": kind,
                "labels": labels[:3] if labels else None,
                "url": url_match.group(1) if url_match else None,
                "phone": phone_norm,
                "count": num or (len(labels) if labels else None)
            })

    # ---- BRAND ----
    if any(w in toks for w in s_brand) or "company name" in lower or "brand name" in lower:
        brand = _extract_brand_name(text)
        if brand:
            directives.append({"type": "set_brand", "name": brand})

    # ---- SHORTEN ----
    if any(w in toks for w in s_shorten) or "make it short" in lower or "make it shorter" in lower:
        target = _extract_int(text) or (((cfg.get("components") or {}).get("text") or {}).get("shorten", {}).get("target_length", 140))
        directives.append({"type": "shorten", "target": int(target)})

    # ---- Setters if explicit key:value ----
    if any(w in toks for w in s_name):
        m = re.search(r'name\s*(?:is|=|as)?\s*["]?([a-z0-9_]{1,64})["]?', text, re.I)
        if m: 
            directives.append({"type": "set_name", "name": m.group(1)})
    if any(w in toks for w in s_body):
        m = re.search(r'(?:body|message|text|content)\s*(?:is|=|:)\s*[""](.+?)[""]', text, re.I|re.S)
        if m: 
            directives.append({"type": "set_body", "text": m.group(1).strip()})
    if any(w in toks for w in s_header):
        m = re.search(r'header\s*(?:is|=|:)\s*[""](.+?)[""]', text, re.I|re.S)
        if m: 
            directives.append({"type": "set_header", "format": "TEXT", "text": m.group(1).strip()})
    if any(w in toks for w in s_footer):
        m = re.search(r'footer\s*(?:is|=|:)\s*[""](.+?)[""]', text, re.I|re.S)
        if m: 
            directives.append({"type": "set_footer", "text": m.group(1).strip()})

    return directives


# --------------------------------------------------------------------------------------
# Apply directives (idempotent, respects category + Meta constraints)
# --------------------------------------------------------------------------------------

def _ensure_buttons_block(comps: list[dict]) -> dict | None:
    return next((c for c in comps if (c.get("type") or "").upper() == "BUTTONS"), None)


def _summarize_buttons(components: list[dict]) -> str:
    for c in (components or []):
        if (c.get("type") or "").upper() == "BUTTONS":
            texts = []
            for b in c.get("buttons", [])[:3]:
                t = (b.get("type") or "QUICK_REPLY").upper()
                label = (b.get("text") or "").strip()
                if t == "URL":
                    label = f"URL: {label or 'Visit Website'}"
                elif t == "PHONE_NUMBER":
                    label = f"CALL: {label or 'Call Us'}"
                texts.append(label or t)
            return " / ".join([x for x in texts if x])
    return ""


def _summarize_header(components: list[dict]) -> str:
    for c in (components or []):
        if (c.get("type") or "").upper() == "HEADER":
            fmt = (c.get("format") or "").upper()
            if fmt == "TEXT":
                return f'TEXT: "{(c.get("text") or '')[:60]}"'
            return fmt
    return ""


def _apply_directives(cfg: Dict[str, Any], directives: list[dict], candidate: Dict[str, Any], memory: Dict[str, Any]) -> tuple[Dict[str, Any], list[str]]:
    """Apply normalized directives in a category-safe, schema-safe way with exact replace support for buttons."""
    out = dict(candidate or {})
    comps = list(out.get("components") or [])
    cat = (out.get("category") or memory.get("category") or "").upper()
    msgs: list[str] = []

    def _get_buttons_block():
        return next((c for c in comps if (c.get("type") or "").upper() == "BUTTONS"), None)

    max_btns = int((((cfg.get("components") or {}).get("buttons") or {}).get("max", 3)) or 3)

    for d in directives:
        t = d.get("type")

        # ---------- BUTTONS: REPLACE EXACT ----------
        if t == "set_buttons":
            if cat == "AUTHENTICATION":
                msgs.append("Buttons aren't allowed for AUTH templates; skipped.")
                continue

            # build exactly from directive
            labels = d.get("labels") or []
            kind = d.get("kind") or "quick"
            btns: list[dict] = []

            if kind == "url" and d.get("url"):
                # single URL button; ignore any extra labels
                btns = [{"type": "URL", "text": labels[0] if labels else "Visit Website", "url": d["url"]}]
            elif kind == "phone" and d.get("phone"):
                btns = [{"type": "PHONE_NUMBER", "text": labels[0] if labels else "Call Us", "phone_number": d["phone"]}]
            else:
                # quick replies
                if not labels:
                    # no labels → fall back to contextual defaults
                    brand = memory.get("brand_name", "")
                    biz = memory.get("business_context") or memory.get("business_type", "")
                    labels = [b["text"] for b in _default_quick_replies(cfg, cat, brand, biz)]
                btns = [{"type": "QUICK_REPLY", "text": l[:20]} for l in labels]

            btns = _cap_buttons_enhanced(btns, max_btns)
            # replace component
            comps = [c for c in comps if (c.get("type") or "").upper() != "BUTTONS"]
            if btns:
                comps.append({"type": "BUTTONS", "buttons": btns})
            out["components"] = comps
            msgs.append(f"Set buttons to: {', '.join(b.get('text') for b in btns)}.")

        # ---------- BUTTONS: ADDITIVE ----------
        elif t == "add_buttons":
            if cat == "AUTHENTICATION":
                msgs.append("Buttons aren't allowed for AUTH templates; skipped.")
                continue

            kind = d.get("kind") or "quick"
            labels = d.get("labels") or []
            count = d.get("count")

            btn_block = _get_buttons_block()
            if not btn_block:
                btn_block = {"type": "BUTTONS", "buttons": []}
                comps.append(btn_block)
            buttons = list(btn_block.get("buttons") or [])

            if kind == "url" and d.get("url"):
                buttons.append({"type": "URL", "text": labels[0] if labels else "Visit Website", "url": d["url"]})
            elif kind == "phone" and d.get("phone"):
                buttons.append({"type": "PHONE_NUMBER", "text": labels[0] if labels else "Call Us", "phone_number": d["phone"]})
            else:
                # quick: use labels if given, else contextual defaults
                if labels:
                    new = [{"type": "QUICK_REPLY", "text": l[:20]} for l in labels]
                else:
                    brand = memory.get("brand_name", "")
                    biz = memory.get("business_context") or memory.get("business_type", "")
                    new = _default_quick_replies(cfg, cat, brand, biz)
                    if count: 
                        new = new[:max(1, min(max_btns, int(count)))]
                buttons.extend(new)

            btn_block["buttons"] = _cap_buttons_enhanced(buttons, max_btns)
            out["components"] = comps
            msgs.append(f"Added {_summarize_buttons_enhanced(btn_block['buttons'])}.")

        # ---------- BRAND ----------
        elif t == "set_brand":
            brand = (d.get("name") or "").strip()
            if brand:
                memory["brand_name"] = brand
                comps = _ensure_brand_in_body(comps, brand)
                out["components"] = comps
                msgs.append(f'Added company name "{brand}" to BODY.')

        # ---------- SHORTEN ----------
        elif t == "shorten":
            target = int(d.get("target") or ((cfg.get("components") or {}).get("text") or {}).get("shorten", {}).get("target_length", 140))
            for c in comps:
                if (c.get("type") or "").upper() == "BODY" and (c.get("text") or "").strip():
                    c["text"] = _shorten_text(c["text"], target)
                    msgs.append(f"Shortened BODY to ≈{target} chars.")
                    break
            out["components"] = comps

        # ---------- NAME/BODY/HEADER/FOOTER ----------
        elif t == "set_name":
            out["name"] = _slug(d.get("name"))
            msgs.append(f"Set name: {out['name']}")
        elif t == "set_body":
            txt = (d.get("text") or "").strip()
            if txt:
                # replace or insert first BODY
                replaced = False
                for c in comps:
                    if (c.get("type") or "").upper() == "BODY":
                        c["text"] = txt
                        replaced = True
                        break
                if not replaced:
                    comps.insert(0, {"type": "BODY", "text": txt})
                out["components"] = comps
                msgs.append("Set BODY.")
        elif t == "set_header":
            fmt = (d.get("format") or "TEXT").upper()
            if cat == "AUTHENTICATION" and fmt != "TEXT":
                msgs.append("For AUTH, only TEXT header is allowed; skipped non-TEXT header.")
                continue
            comps = [c for c in comps if (c.get("type") or "").upper() != "HEADER"]
            h = {"type": "HEADER", "format": fmt}
            if fmt == "TEXT":
                txt = (d.get("text") or "").strip()
                if txt: 
                    h["text"] = txt[:60]
            out["components"] = [h] + comps
            msgs.append("Set HEADER.")
        elif t == "set_footer":
            txt = (d.get("text") or "").strip()
            seen = False
            for c in comps:
                if (c.get("type") or "").upper() == "FOOTER":
                    c["text"] = txt[:60]
                    seen = True
                    break
            if not seen: 
                comps.append({"type": "FOOTER", "text": txt[:60]})
            out["components"] = comps
            msgs.append("Set FOOTER.")

    return out, msgs


# --------------------------------------------------------------------------------------
# Draft sanitization / schema preparation
# --------------------------------------------------------------------------------------

def _has_component(p: Dict[str, Any], kind: str) -> bool:
    return any(isinstance(c, dict) and (c.get("type") or "").upper() == kind for c in (p.get("components") or []))


def _sanitize_candidate(cand: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(cand, dict):
        return {}
    c = dict(cand)

    for k in ("required", "component_types", "button_types", "body_required"):
        c.pop(k, None)

    pattern = re.compile(r"^[a-z0-9_]{1,64}$")
    if "name" in c and isinstance(c["name"], str) and c["name"].strip():
        nm = c["name"].strip()
        c["name"] = nm if pattern.match(nm) else _slug(nm)

    if "language" in c:
        lang = _normalize_language(c.get("language"))
        if lang: c["language"] = lang
        else: c.pop("language", None)

    if "category" in c and isinstance(c["category"], str) and c["category"].strip():
        cat = c["category"].strip().upper()
        c["category"] = cat if cat in ("MARKETING", "UTILITY", "AUTHENTICATION") else c.pop("category", None)

    for k in ("name", "language", "category"):
        if k in c and isinstance(c[k], str) and not c[k].strip():
            c.pop(k, None)

    comps = c.get("components")
    if isinstance(comps, list):
        clean = []
        collected_buttons = []
        for comp in comps:
            if not isinstance(comp, dict):
                continue
            t = (comp.get("type") or "").strip().upper()
            if t == "BODY":
                txt = (comp.get("text") or "").strip()
                if txt:
                    out = {"type": "BODY", "text": txt}
                    if "example" in comp: out["example"] = comp["example"]
                    clean.append(out)
            elif t == "HEADER":
                fmt = (comp.get("format") or "").strip().upper()
                txt = (comp.get("text") or "").strip()
                if not fmt and txt:
                    fmt = "TEXT"
                if fmt == "TEXT" and txt:
                    item = {"type": "HEADER", "format": "TEXT", "text": txt}
                    if "example" in comp: item["example"] = comp["example"]
                    clean.append(item)
                elif fmt in {"IMAGE", "VIDEO", "DOCUMENT", "LOCATION"}:
                    item = {"type": "HEADER", "format": fmt}
                    if "example" in comp: item["example"] = comp["example"]
                    clean.append(item)
            elif t == "FOOTER":
                txt = (comp.get("text") or "").strip()
                if txt:
                    clean.append({"type": "FOOTER", "text": txt})
            elif t == "BUTTONS":
                btns = comp.get("buttons")
                if isinstance(btns, list) and btns:
                    b2 = []
                    for b in btns:
                        if not isinstance(b, dict):
                            continue
                        btn_text = b.get("text") or b.get("label") or b.get("title") or b.get("value")
                        btn_type = b.get("type", "QUICK_REPLY")
                        if not btn_text:
                            continue
                        # Enforce 20-character limit for button text
                        btn_text = str(btn_text).strip()[:20]
                        if btn_type.lower() in ("reply", "button"):
                            btn_type = "QUICK_REPLY"
                        elif btn_type.upper() not in ("QUICK_REPLY", "URL", "PHONE_NUMBER"):
                            btn_type = "QUICK_REPLY"
                        btn = {"type": btn_type, "text": btn_text}
                        if b.get("payload"): btn["payload"] = b["payload"]
                        if btn_type == "URL":
                            url = b.get("url")
                            if not url: continue
                            btn["url"] = url
                        elif btn_type == "PHONE_NUMBER":
                            phone = b.get("phone_number")
                            if not phone: continue
                            btn["phone_number"] = phone
                        b2.append(btn)
                    if b2:
                        clean.append({"type": "BUTTONS", "buttons": b2})
                elif comp.get("text") or comp.get("label") or comp.get("title"):
                    btn_text = (comp.get("text") or comp.get("label") or comp.get("title") or "").strip()[:20]
                    btn_type = comp.get("button_type") or "QUICK_REPLY"
                    if btn_text:
                        btn = {"type": btn_type, "text": btn_text}
                        if comp.get("payload"): btn["payload"] = comp["payload"]
                        collected_buttons.append(btn)
        if collected_buttons:
            clean.append({"type": "BUTTONS", "buttons": collected_buttons})
        if clean:
            c["components"] = clean
        else:
            c.pop("components", None)
    elif "components" in c:
        c.pop("components", None)

    # Flat fields → components
    components = c.get("components", [])
    body_value = c.get("BODY") or c.get("body")
    if body_value and isinstance(body_value, str) and body_value.strip():
        if not any(isinstance(x, dict) and x.get("type") == "BODY" for x in components):
            components.insert(0, {"type": "BODY", "text": body_value.strip()})
        c.pop("BODY", None); c.pop("body", None)
    header_value = c.get("HEADER") or c.get("header")
    if header_value and isinstance(header_value, str) and header_value.strip():
        if not any(isinstance(x, dict) and x.get("type") == "HEADER" for x in components):
            components.append({"type": "HEADER", "format": "TEXT", "text": header_value.strip()})
        c.pop("HEADER", None); c.pop("header", None)
    footer_value = c.get("FOOTER") or c.get("footer")
    if footer_value and isinstance(footer_value, str) and footer_value.strip():
        if not any(isinstance(x, dict) and x.get("type") == "FOOTER" for x in components):
            components.append({"type": "FOOTER", "text": footer_value.strip()})
        c.pop("FOOTER", None); c.pop("footer", None)
    if components:
        c["components"] = components

    # Root-level buttons → component
    if "buttons" in c and c["buttons"]:
        components = c.get("components", [])
        if not any(isinstance(comp, dict) and comp.get("type") == "BUTTONS" for comp in components):
            normalized = []
            for btn in c.pop("buttons"):
                if isinstance(btn, dict):
                    if btn.get("type") == "reply" and btn.get("reply"):
                        reply = btn["reply"]
                        nb = {"type": "QUICK_REPLY", "text": (reply.get("title") or reply.get("text", "Button"))[:20]}
                        if reply.get("id"): nb["payload"] = reply["id"]
                        normalized.append(nb)
                    else:
                        btn_text = (btn.get("text") or btn.get("title") or btn.get("label") or btn.get("value") or "Button")[:20]
                        btn_type = btn.get("type", "QUICK_REPLY")
                        if btn_type.lower() in ("reply", "button"): btn_type = "QUICK_REPLY"
                        elif btn_type.upper() not in ("QUICK_REPLY", "URL", "PHONE_NUMBER"): btn_type = "QUICK_REPLY"
                        nb = {"type": btn_type, "text": btn_text}
                        if btn.get("payload"): nb["payload"] = btn["payload"]
                        if btn.get("url"): nb["url"] = btn["url"]
                        if btn.get("phone_number"): nb["phone_number"] = btn["phone_number"]
                        normalized.append(nb)
            if normalized:
                components.append({"type": "BUTTONS", "buttons": normalized})
                c["components"] = components
        else:
            c.pop("buttons", None)

    return c


def _strip_non_schema_button_fields(candidate: Dict[str, Any]) -> None:
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
    allowed = {
        "BODY": {"type", "text", "example"},
        "HEADER": {"type", "format", "text", "example"},
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


def _compute_missing(p: Dict[str, Any], memory: Dict[str, Any]) -> List[str]:
    miss: List[str] = []
    if not p.get("category"): miss.append("category")
    if not p.get("language"): miss.append("language")
    if not p.get("name"):     miss.append("name")
    has_body = any(
        isinstance(c, dict) and (c.get("type") or "").upper() == "BODY" and (c.get("text") or "").strip()
        for c in (p.get("components") or [])
    )
    if not has_body: miss.append("body")

    cat = (p.get("category") or memory.get("category") or "").upper()
    skip_extras = (memory.get("extras_choice") == "skip")
    if cat == "AUTHENTICATION":
        if memory.get("wants_header") and not _has_component(p, "HEADER"):
            miss.append("header")
    elif not skip_extras:
        if memory.get("wants_header") and not _has_component(p, "HEADER"): miss.append("header")
        if memory.get("wants_footer") and not _has_component(p, "FOOTER"): miss.append("footer")
        if memory.get("wants_buttons") and not _has_component(p, "BUTTONS"): miss.append("buttons")
    return miss


def _minimal_scaffold(mem: Dict[str, Any]) -> Dict[str, Any]:
    cat = (mem.get("category") or "").upper()
    if cat not in {"MARKETING", "UTILITY", "AUTHENTICATION"}:
        return {}
    lang = mem.get("language_pref") or mem.get("language") or "en_US"
    event = mem.get("event_label") or mem.get("event") or "offer"
    business = mem.get("business_type") or mem.get("business") or "brand"
    name = mem.get("proposed_name") or f"{_slug(event)}_{_slug(business)}_v{dt.datetime.utcnow().strftime('%m%d')}"
    components: List[Dict[str, Any]] = []
    if cat == "AUTHENTICATION":
        body = "{{1}} is your verification code. Do not share this code. It expires in {{2}} minutes."
        components.append({"type": "BODY", "text": body})
        return {"category": cat, "language": lang, "name": name, "components": components}
    body = "Hi {{1}}, {event}! Enjoy {{2}}.".format(event=event)
    if cat == "UTILITY":
        body = "Hello {{1}}, your {{2}} has been updated. Latest status: {{3}}."
    components.append({"type": "BODY", "text": body})
    return {"category": cat, "language": lang, "name": name, "components": components}


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
        "skip", "no buttons", "no header", "no footer", "finalize as is", "looks good as is", "no extras"
    ])


def _targeted_missing_reply(missing: List[str], memory: Dict[str, Any] = None) -> str:
    if "buttons" in missing and memory and (memory.get("category") or "").upper() == "AUTHENTICATION":
        return "Buttons aren't allowed for authentication templates; I'll proceed without them. Want a short TEXT header?"
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
        return "You asked for buttons. Should I add quick replies like 'View offers' and 'Order now'?"
    if "footer" in missing:
        return "You asked for a footer. Should I add a short footer like 'Thank you!'?"
    return "What would you like me to add next?"


# --------------------------------------------------------------------------------------
# Session APIs
# --------------------------------------------------------------------------------------

@app.get("/session/{session_id}", response_model=SessionData)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    s = await get_or_create_session(db, session_id)
    current_draft = {}
    if s.active_draft_id:
        draft = await db.get(Draft, s.active_draft_id)
        if draft:
            current_draft = draft.draft or {}
    messages_data = (s.data or {}).get("messages", [])
    messages = [ChatMessage(role=msg["role"], content=msg["content"]) for msg in messages_data]
    return SessionData(
        session_id=s.id,
        messages=messages,
        draft=current_draft,
        memory=s.memory or {},
        last_action=s.last_action,
        updated_at=s.updated_at.isoformat() if s.updated_at else "",
    )


# --------------------------------------------------------------------------------------
# Chat endpoint (concise confirmations, dynamic summaries, robust button ops)
# --------------------------------------------------------------------------------------

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

    # 2) Build LLM inputs + classify
    system = build_friendly_system_prompt(cfg)
    context = build_context_block(draft, memory, cfg, msgs)
    safe_message = _sanitize_user_input(inp.message)

    low = safe_message.lower()
    if "header" in low: memory["wants_header"] = True
    if "footer" in low: memory["wants_footer"] = True
    if "button" in low or "buttons" in low: memory["wants_buttons"] = True

    # Simple category heuristic for promotions
    if not memory.get("category") and not draft.get("category"):
        if any(k in low for k in ["promotional", "promotion", "offer", "discount", "sale", "special", "deal"]):
            memory["category"] = "MARKETING"; draft["category"] = "MARKETING"

    # Extract business type broadly
    if not memory.get("business_type"):
        memory["business_type"] = _detect_business_type(safe_message, memory.get("brand_name", ""))

    # Extract brand name if provided
    if not memory.get("brand_name"):
        brand = _extract_brand_name(safe_message)
        if brand:
            memory["brand_name"] = brand

    s.memory = memory

    # Auto-name session on first message
    if inp.user_id and len(msgs) == 0:
        from sqlalchemy import select
        user = (await db.execute(select(User).where(User.user_id == inp.user_id))).scalar_one_or_none()
        if user:
            await upsert_user_session(db, inp.user_id, s.id, None)

    llm = LlmClient(model=cfg.get("model", "gpt-4o-mini"), temperature=float(cfg.get("temperature", 0.2)))

    # Log request (scrubbed)
    log_user = scrub_sensitive_data(safe_message)
    await log_llm(db, s.id, "request", _redact_secrets({
        "system": system, "context": context, "history": msgs,
        "user": log_user, "state": memory.get("_system_state"), "intent": memory.get("_user_intent")
    }), cfg.get("model"), None)

    try:
        out = llm.respond(system, context, msgs, safe_message)
        if not isinstance(out, dict):
            out = {"agent_action": "ASK", "message_to_user": _fallback_reply_for_state("need_category")}
        out.setdefault("agent_action", "ASK")
        out.setdefault("message_to_user", "")
        out.setdefault("draft", None)
        out.setdefault("missing", [])
        out.setdefault("final_creation_payload", None)
        out.setdefault("memory", {})
    except Exception as e:
        await log_llm(db, s.id, "error", _redact_secrets({"error": str(e), "user_input": log_user}), cfg.get("model"), None)
        fallback = _fallback_reply_for_state("need_category")
        await db.commit()
        return ChatResponse(session_id=s.id, reply=fallback, draft=draft, missing=_compute_missing(draft, memory), final_creation_payload=None)

    await log_llm(db, s.id, "response", _redact_secrets(out), cfg.get("model"), out.get("_latency_ms"))

    # 3) Extract + normalize
    action = str(out.get("agent_action") or "ASK").upper()
    reply = (out.get("message_to_user") or "").strip()
    candidate = out.get("final_creation_payload") or out.get("draft") or {}
    if not isinstance(candidate, dict):
        candidate = {}

    mem_update = out.get("memory") or {}
    if mem_update:
        memory = merge_deep(memory, mem_update)
        s.memory = memory
    if _user_declined_extras(safe_message):
        memory = merge_deep(memory, {"extras_choice": "skip"})
        for k in ("wants_header", "wants_footer", "wants_buttons"):
            memory.pop(k, None)
        s.memory = memory

    def _append_history(user_text: str, assistant_text: str) -> List[Dict[str, str]]:
        new_hist = msgs + [{"role": "user", "content": user_text}, {"role": "assistant", "content": assistant_text}]
        return new_hist[-max_turns:]

    # Helper to persist a turn
    async def _persist_turn_and_return(reply_text: str, new_draft: Dict[str, Any], missing_list: List[str]):
        s.last_action = action
        s.last_question_hash = _qhash(reply_text) if reply_text.endswith("?") else None
        s.data = {**(s.data or {}), "messages": _append_history(inp.message, reply_text)}
        await touch_user_session(db, inp.user_id, s.id)
        await upsert_session(db, s); await db.commit()
        return ChatResponse(session_id=s.id, reply=reply_text, draft=new_draft, missing=missing_list, final_creation_payload=None)

    # Let LLM pin category if provided
    category = (candidate.get("category") or memory.get("category") or draft.get("category"))
    if category and not memory.get("category"):
        s.memory = merge_deep(memory, {"category": category})

    # 4) Non-FINAL path: sanitize + directives + dynamic confirmations
    if action in {"ASK", "DRAFT", "UPDATE", "CHITCHAT"}:
        candidate = _sanitize_candidate(candidate) if candidate else {}
        candidate = merge_deep(draft, candidate) if candidate else draft

        # opportunistic language normalization
        if not candidate.get("language"):
            lang_guess = _normalize_language(safe_message)
            if lang_guess:
                candidate["language"] = lang_guess

        # Apply directives (buttons/name/body/brand/shorten/header/footer)
        directives = _parse_user_directives(cfg, safe_message)
        msgs_applied: List[str] = []
        if directives:
            candidate, msgs_applied = _apply_directives(cfg, directives, candidate, memory)

        # If brand pending and BODY exists later, inject
        if memory.get("brand_name_pending") and any((c.get("type") or "").upper() == "BODY" for c in (candidate.get("components") or [])):
            candidate["components"] = _ensure_brand_in_body(candidate.get("components") or [], memory.pop("brand_name_pending"))
            msgs_applied.append("Added stored brand to BODY.")

        d.draft = candidate

        # Compute missing
        computed_missing = _compute_missing(candidate, memory)
        llm_missing = (out.get("missing") or [])
        extras_present = {"header": _has_component(candidate, "HEADER"), "buttons": _has_component(candidate, "BUTTONS"), "footer": _has_component(candidate, "FOOTER")}
        llm_missing = [m for m in llm_missing if m not in ("header", "buttons", "footer") or not extras_present.get(m, False)]
        core = [m for m in computed_missing if m in ["category", "language", "name", "body"]]
        missing = list(dict.fromkeys(llm_missing + core))

        # Compose reply (concise, deterministic if we applied edits)
        ui_cfg = (cfg.get("ui") or {})
        enc_cfg = (ui_cfg.get("encouragement") or {})
        tone = (ui_cfg.get("tone") or "neutral").lower()
        enc_enabled = bool(enc_cfg.get("enabled", False))
        
        if msgs_applied:
            # If LLM gave nothing or generic, replace; else append succinctly
            if not reply or reply.lower().startswith("please tell me more"):
                reply = "; ".join(msgs_applied) + ". Anything else to add?"
            else:
                reply = (reply + "\n\nApplied: " + "; ".join(msgs_applied)).strip()
        if not reply:
            reply = _targeted_missing_reply(missing, memory)

        # Remove hardcoded button confirmations - let msgs_applied handle it
        # No dynamic button/header summaries needed since msgs_applied provides exact details

        # Trim tone (remove excessive enthusiasm unless friendly mode enabled)
        if tone == "neutral" or not enc_enabled:
            reply = re.sub(r"\s*(?:Great progress!|Looking good!|Perfect!|Excellent!|Nice work!|Fantastic!|You're doing great!|This is looking really professional!|You're creating something.*?appreciate!|.*?beautifully!|.*?\u2728)", "", reply).strip()

        return await _persist_turn_and_return(reply, candidate, missing)

    # 5) FINAL path: enforce header rules, validate, finalize
    if action == "FINAL":
        candidate = _sanitize_candidate(candidate) if candidate else {}
        candidate = candidate or draft or _minimal_scaffold(memory)

        # AUTH header gate
        cat = (candidate.get("category") or memory.get("category") or "").upper()
        if cat == "AUTHENTICATION":
            for comp in (candidate.get("components") or []):
                if isinstance(comp, dict) and (comp.get("type") or "").upper() == "HEADER":
                    if (comp.get("format") or "").upper() != "TEXT":
                        d.draft = merge_deep(draft, candidate)
                        s.last_action = "ASK"
                        msg = "Authentication templates only allow TEXT headers. Please use a short text header or remove it."
                        s.data = {**(s.data or {}), "messages": _append_history(inp.message, msg)}
                        await touch_user_session(db, inp.user_id, s.id)
                        await upsert_session(db, s); await db.commit()
                        return ChatResponse(session_id=s.id, reply=msg, draft=d.draft, missing=_compute_missing(d.draft, memory), final_creation_payload=None)

        # Enforce requested extras for non-AUTH
        def _has_component_kind(p: Dict[str, Any], kind: str) -> bool:
            return any(isinstance(c, dict) and (c.get("type") or "").upper() == kind for c in (p.get("components") or []))

        missing_extras = []
        if cat != "AUTHENTICATION":
            if memory.get("wants_header") and not _has_component_kind(candidate, "HEADER"): missing_extras.append("header")
            if memory.get("wants_footer") and not _has_component_kind(candidate, "FOOTER"): missing_extras.append("footer")
            if memory.get("wants_buttons") and not _has_component_kind(candidate, "BUTTONS"): missing_extras.append("buttons")
        if missing_extras:
            d.draft = merge_deep(draft, candidate)
            s.last_action = "ASK"
            ask = _targeted_missing_reply(missing_extras, memory)
            s.data = {**(s.data or {}), "messages": _append_history(inp.message, ask)}
            await touch_user_session(db, inp.user_id, s.id)
            await upsert_session(db, s); await db.commit()
            return ChatResponse(session_id=s.id, reply=ask, draft=d.draft, missing=_compute_missing(d.draft, memory), final_creation_payload=None)

        schema = cfg.get("creation_payload_schema", {}) or {}
        candidate_for_validation = copy.deepcopy(candidate)
        _strip_component_extras(candidate_for_validation)
        _strip_non_schema_button_fields(candidate_for_validation)
        issues = validate_schema(candidate_for_validation, schema)
        issues += lint_rules(candidate_for_validation, cfg.get("lint_rules", {}) or {})

        if issues:
            d.draft = merge_deep(draft, candidate)
            s.last_action = "ASK"
            final_reply = (reply + ("\n\nPlease fix: " + "; ".join(issues) if issues else "")).strip() or "Please address the validation issues."
            ui_cfg = (cfg.get("ui") or {})
            tone = (ui_cfg.get("tone") or "neutral").lower()
            if tone == "neutral":
                final_reply = re.sub(r"\s*(Great progress!|Looking good!|Perfect!|Excellent!|Nice work!|Fantastic!).*$", "", final_reply)
            s.data = {**(s.data or {}), "messages": _append_history(inp.message, final_reply)}
            await touch_user_session(db, inp.user_id, s.id)
            await upsert_session(db, s); await db.commit()
            return ChatResponse(session_id=s.id, reply=final_reply, draft=d.draft, missing=_compute_missing(d.draft, memory) + ["fix_validation_issues"], final_creation_payload=None)

        # Finalize
        d.finalized_payload = candidate_for_validation
        d.status = "FINAL"
        d.draft = candidate
        s.last_action = "FINAL"
        done_msg = reply or "Finalized."
        ui_cfg = (cfg.get("ui") or {})
        tone = (ui_cfg.get("tone") or "neutral").lower()
        if tone == "neutral":
            done_msg = done_msg.replace("Awesome!", "").strip()
        s.data = {**(s.data or {}), "messages": _append_history(inp.message, done_msg)}
        await touch_user_session(db, inp.user_id, s.id)
        await upsert_session(db, s); await db.commit()
        return ChatResponse(session_id=s.id, reply=done_msg, draft=d.draft, missing=None, final_creation_payload=candidate_for_validation)

    # 6) Fallback → ASK
    final_draft = candidate or draft
    d.draft = final_draft
    s.last_action = "ASK"
    missing = _compute_missing(final_draft, memory)
    final_reply = reply or _targeted_missing_reply(missing, memory)

    if final_reply.endswith("?"):
        qh = _qhash(final_reply)
        if s.last_question_hash == qh and _is_affirmation(safe_message):
            base = dict(final_draft)
            if "language" in missing:
                base["language"] = _normalize_language(safe_message) or memory.get("language_pref") or "en_US"
            if "name" in missing and any(k in safe_message.lower() for k in ["you choose", "suggest", "pick a name"]):
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
    return ChatResponse(session_id=s.id, reply=final_reply, draft=final_draft, missing=missing, final_creation_payload=None)


# --------------------------------------------------------------------------------------
# Welcome helper (kept minimal)
# --------------------------------------------------------------------------------------
@app.get("/welcome")
async def get_welcome_message():
    return {
        "message": "Welcome! Describe the message you want to send, and we’ll create a WhatsApp template.",
        "journey_stage": "welcome",
        "next_steps": [
            "Tell me your goal (e.g., greeting, offer, confirmation)",
            "Describe your business (optional)",
            "Say if you want header/footer/buttons",
        ],
    }
