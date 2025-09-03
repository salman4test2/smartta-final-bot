from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.engine.url import make_url
import os, re, datetime as dt, hashlib

from .db import engine, SessionLocal, Base
from .models import Draft, User, UserSession
from .repo import (
    get_or_create_session, upsert_session, create_draft,
    log_llm, upsert_user_session, touch_user_session
)
from .config import get_config, get_cors_origins, is_production
from .prompts import build_context_block, build_friendly_system_prompt
from .llm import LlmClient
from .validator import validate_schema, lint_rules
from .schemas import ChatInput, ChatResponse, SessionData, ChatMessage
from .utils import merge_deep, scrub_sensitive_data as scrub_for_logs
from .directives import parse_directives, apply_directives, ensure_brand_in_body

# Route modules
from .routes import config as cfg_routes, debug, users, sessions
# If you added interactive router, keep this import
try:
    from .interactive import router as interactive_router
except Exception:
    interactive_router = None

app = FastAPI(title="LLM-First WhatsApp Template Builder", version="4.1.0")

# Routers
app.include_router(cfg_routes.router)
app.include_router(debug.router)
app.include_router(users.router)
app.include_router(sessions.router)
if interactive_router:
    app.include_router(interactive_router)

# ---------- CORS ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Utils ----------
def _qhash(s: str) -> str:
    return hashlib.sha1((s or "").encode("utf-8")).hexdigest()[:12]

LANG_MAP = {
    "english": "en_US", "en": "en_US", "en_us": "en_US", "english_us": "en_US",
    "hindi": "hi_IN", "hi": "hi_IN", "hi_in": "hi_IN", "hindi_in": "hi_IN",
    "spanish": "es_MX", "es": "es_MX", "es_mx": "es_MX", "spanish_mx": "es_MX",
}

AFFIRM_RE = re.compile(
    r'^\s*(yes|y|ok|okay|sure|sounds\s+good|go\s+ahead|please\s+proceed|proceed|confirm|finalize|do\s+it)\b',
    re.I
)

def _normalize_language(s: Optional[str]) -> Optional[str]:
    if not s: return None
    key = re.sub(r'[^a-z_]', '', s.strip().lower().replace("-", "_").replace(" ", "_"))
    return LANG_MAP.get(key, s if "_" in s else None)

def _is_affirmation(text: str) -> bool:
    return bool(AFFIRM_RE.match(text or ""))

def _sanitize_user_input(text: Any) -> str:
    if not isinstance(text, str):
        return ""
    t = text.strip()
    if len(t) > 2000: t = t[:2000]
    # Light protection against role injection; DO NOT scrub business data here.
    for pattern in [
        r"(?i)system\s*:", r"(?i)assistant\s*:",
        r"(?i)ignore\s+previous\s+instructions",
        r"(?i)forget\s+everything", r"(?i)act\s+as\s+if", r"\{\{\s*\{\{",
    ]:
        t = re.sub(pattern, " ", t)
    return t.strip()

def _generate_session_name_from_message(message: str, category: Optional[str] = None) -> str:
    clean = re.sub(r'[^\w\s]', '', (message or "").lower()).split()
    stop = {'i','want','to','create','a','for','the','and','or','but','make','template','whatsapp'}
    words = [w for w in clean if w not in stop and len(w) > 2][:4] or ["new"]
    cat = (category or "").upper()
    add = {"MARKETING": "promotion", "UTILITY": "notification", "AUTHENTICATION": "verification"}.get(cat)
    if add: words.append(add)
    return f"{' '.join(words).title()} Template"

def _ack(cfg: Dict[str, Any], fallback: str = "Updated.") -> str:
    """Return a neutral/confirmative phrase per UI config."""
    ui = (cfg.get("ui") or {})
    style = ((ui.get("confirmations") or {}).get("style") or "neutral").lower()
    phrases = ((ui.get("confirmations") or {}).get("neutral_phrases") or ["Updated."])
    if style == "neutral" and phrases:
        return phrases[0]
    return fallback

def _compute_missing(p: Dict[str, Any], memory: Dict[str, Any]) -> List[str]:
    """Keep this small; detailed rules live in validator + YAML."""
    miss: List[str] = []
    if not p.get("category"): miss.append("category")
    if not p.get("language"): miss.append("language")
    if not p.get("name"):     miss.append("name")
    comps = p.get("components") or []
    has_body = any(isinstance(c, dict) and (c.get("type") or "").upper()=="BODY" and (c.get("text") or "").strip() for c in comps)
    if not has_body: miss.append("body")

    # Honor user's explicit extras choices but do NOT hardcode category bans here.
    if memory.get("wants_header") and not any((c.get("type") or "").upper()=="HEADER" for c in comps): miss.append("header")
    if memory.get("wants_footer") and not any((c.get("type") or "").upper()=="FOOTER" for c in comps): miss.append("footer")
    if memory.get("wants_buttons") and not any((c.get("type") or "").upper()=="BUTTONS" for c in comps): miss.append("buttons")
    return miss

def _fallback_reply_for_state(state: str) -> str:
    if state == "need_category":
        return "Which template type do you want: MARKETING, UTILITY, or AUTHENTICATION?"
    if state == "need_language":
        return "Which language code should we use (e.g., en_US, hi_IN)?"
    if state == "need_name":
        return "What should we name this template (snake_case, e.g., diwali_offer)?"
    if state == "need_body":
        return "What should the main message (BODY) say?"
    return "Could you share a bit more about the template you want to create?"

def _determine_state(draft: Dict[str, Any], memory: Dict[str, Any]) -> str:
    has_category = bool(draft.get("category") or memory.get("category"))
    has_language = bool(draft.get("language") or memory.get("language_pref"))
    has_name = bool(draft.get("name"))
    has_body = any(isinstance(c, dict) and c.get("type") == "BODY" and (c.get("text") or "").strip()
                   for c in (draft.get("components") or []))
    if not has_category: return "need_category"
    if not has_language: return "need_language"
    if not has_name:     return "need_name"
    if not has_body:     return "need_body"
    return "ready"

async def get_db() -> AsyncSession:
    async with SessionLocal() as s:
        yield s

# ---------- Startup ----------
@app.on_event("startup")
async def on_startup():
    try:
        safe = make_url(os.getenv("DATABASE_URL", "")).set(password="***")
        print(f"[DEBUG] startup: DATABASE_URL={safe}")
    except Exception:
        pass

    async with engine.begin() as aconn:
        await aconn.run_sync(Base.metadata.create_all)

    try:
        if engine.url.drivername.startswith("sqlite"):
            if is_production():
                print("[WARNING] SQLite in production. Consider PostgreSQL.")
            async with engine.begin() as aconn:
                await aconn.exec_driver_sql("PRAGMA journal_mode=WAL;")
                await aconn.exec_driver_sql("PRAGMA synchronous=NORMAL;")
                await aconn.exec_driver_sql("PRAGMA foreign_keys=ON;")
    except Exception:
        pass

# ---------- Endpoints ----------

@app.get("/session/{session_id}", response_model=SessionData)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    s = await get_or_create_session(db, session_id)
    draft_payload: Dict[str, Any] = {}
    if s.active_draft_id:
        d = await db.get(Draft, s.active_draft_id)
        if d: draft_payload = d.draft or {}
    msgs = (s.data or {}).get("messages", [])
    messages = [ChatMessage(role=m["role"], content=m["content"]) for m in msgs]
    return SessionData(
        session_id=s.id,
        messages=messages,
        draft=draft_payload,
        memory=s.memory or {},
        last_action=s.last_action,
        updated_at=(s.updated_at.isoformat() if s.updated_at else "")
    )

@app.post("/chat", response_model=ChatResponse)
async def chat(inp: ChatInput, db: AsyncSession = Depends(get_db)):
    cfg = get_config()
    hist = (cfg.get("history") or {})
    max_turns = int(hist.get("max_turns", 200))

    # 1) session + draft
    s = await get_or_create_session(db, inp.session_id)
    if not s.active_draft_id:
        d = await create_draft(db, s.id, draft={}, version=1)
        s.active_draft_id = d.id
        await db.flush()
    else:
        d = await db.get(Draft, s.active_draft_id) or await create_draft(db, s.id, draft={}, version=1)
        s.active_draft_id = d.id

    draft: Dict[str, Any] = dict(d.draft or {})
    memory: Dict[str, Any] = dict(s.memory or {})
    msgs: List[Dict[str, str]] = (s.data or {}).get("messages", [])

    # 2) build LLM inputs
    system = build_friendly_system_prompt(cfg)
    context = build_context_block(draft, memory, cfg, msgs)
    user_msg_raw = inp.message
    user_msg = _sanitize_user_input(user_msg_raw)

    # 2.1 log request (use scrubbed copy)
    await log_llm(
        db, s.id, "request",
        {"system": system, "context": context, "history": msgs,
         "user": scrub_for_logs(user_msg), "state": _determine_state(draft, memory)},
        cfg.get("model"), None
    )

    # 2.2 optional association + session auto-naming
    if inp.user_id and not msgs:
        from sqlalchemy import select, update
        user = (await db.execute(select(User).where(User.user_id == inp.user_id))).scalar_one_or_none()
        if user:
            await upsert_user_session(db, inp.user_id, s.id, None)
            category = draft.get("category") or memory.get("category")
            us = (await db.execute(
                select(UserSession).where(UserSession.user_id==inp.user_id, UserSession.session_id==s.id)
            )).scalar_one_or_none()
            if us and not us.session_name:
                name = _generate_session_name_from_message(user_msg, category)
                await db.execute(
                    update(UserSession).where(UserSession.user_id==inp.user_id, UserSession.session_id==s.id)
                    .values(session_name=name)
                )

    # 3) call LLM
    llm = LlmClient(model=cfg.get("model", "gpt-4o-mini"),
                    temperature=float(cfg.get("temperature", 0.2)))
    try:
        out = llm.respond(system, context, msgs, user_msg) or {}
    except Exception as e:
        await log_llm(db, s.id, "error", {"error": str(e)}, cfg.get("model"), None)
        fb = _fallback_reply_for_state(_determine_state(draft, memory))
        await db.commit()
        return ChatResponse(session_id=s.id, reply=fb, draft=draft,
                            missing=_compute_missing(draft, memory),
                            final_creation_payload=None)

    await log_llm(db, s.id, "response", out, cfg.get("model"), out.get("_latency_ms"))

    # 4) interpret model output (LLM-first; no hardcoded branching)
    action = (out.get("agent_action") or "ASK").upper()
    reply_from_llm = (out.get("message_to_user") or "").strip()
    candidate = out.get("final_creation_payload") or out.get("draft") or {}
    if not isinstance(candidate, dict):
        candidate = {}

    # memory updates from LLM
    mem_update = out.get("memory") or {}
    if mem_update:
        memory = merge_deep(memory, mem_update)
        s.memory = memory

    # 5) apply deterministic directives (config-driven), no hardcode
    directives = parse_directives(cfg, user_msg)
    if directives:
        candidate, directive_msgs = apply_directives(cfg, directives, candidate, memory)
    else:
        directive_msgs = []

    # If brand was stored pending and BODY appears, inject now (deterministic)
    if memory.get("brand_name_pending"):
        comps = candidate.get("components") or []
        if any((c.get("type") or "").upper()=="BODY" for c in comps):
            candidate["components"] = ensure_brand_in_body(comps, memory.pop("brand_name_pending"))

    # 6) opportunistic language detection
    if not candidate.get("language"):
        lang_guess = _normalize_language(user_msg)
        if lang_guess:
            candidate["language"] = lang_guess

    # 7) merge with current draft
    merged = merge_deep(draft, candidate) if candidate else draft
    d.draft = merged

    # 8) compute missing (light), then validate strictly on FINAL
    missing = _compute_missing(merged, memory)
    state = _determine_state(merged, memory)

    def _append_history(user_text: str, assistant_text: str) -> List[Dict[str, str]]:
        new = msgs + [{"role": "user", "content": user_text},
                      {"role": "assistant", "content": assistant_text}]
        return new[-max_turns:]

    # Prepare neutral confirmation if directives changed content
    confirmation = None
    if directive_msgs:
        # Example: "Added 1 quick reply (Get Now)." — strictly reflects applied change
        confirmation = f"{'; '.join(directive_msgs)}"

    # 9) Non-FINAL (ASK/DRAFT/UPDATE/CHITCHAT)
    if action in {"ASK", "DRAFT", "UPDATE", "CHITCHAT"}:
        # Prefer LLM reply; if it's generic, use deterministic confirmation or a targeted question
        reply_text = reply_from_llm or confirmation or _fallback_reply_for_state(state)
        # Avoid “button?” loops: if we actually added the buttons, confirm cleanly
        if confirmation and ("button" in confirmation.lower() or "reply" in confirmation.lower()):
            reply_text = confirmation

        s.last_action = action
        s.last_question_hash = _qhash(reply_text) if reply_text.endswith("?") else None
        s.data = {**(s.data or {}), "messages": _append_history(inp.message, reply_text)}
        await touch_user_session(db, inp.user_id, s.id)
        await upsert_session(db, s); await db.commit()
        return ChatResponse(session_id=s.id, reply=reply_text, draft=merged,
                            missing=missing, final_creation_payload=None)

    # 10) FINAL: validate with schema+lint (all deep rules live in validator/YAML)
    if action == "FINAL":
        # Validate a schema-clean copy
        import copy
        to_validate = copy.deepcopy(merged)
        issues = validate_schema(to_validate, cfg.get("creation_payload_schema", {}) or {})
        issues += lint_rules(to_validate, cfg.get("lint_rules", {}) or {})

        if issues:
            msg = (reply_from_llm or _ack(cfg)) + "\n\nPlease fix: " + "; ".join(issues)
            s.last_action = "ASK"
            s.data = {**(s.data or {}), "messages": _append_history(inp.message, msg)}
            await touch_user_session(db, inp.user_id, s.id)
            await upsert_session(db, s); await db.commit()
            return ChatResponse(session_id=s.id, reply=msg, draft=merged,
                                missing=_compute_missing(merged, memory) + ["fix_validation_issues"],
                                final_creation_payload=None)

        # Finalize
        d.finalized_payload = to_validate
        d.status = "FINAL"
        s.last_action = "FINAL"
        final_msg = reply_from_llm or _ack(cfg, "Finalized.")
        s.data = {**(s.data or {}), "messages": _append_history(inp.message, final_msg)}
        await touch_user_session(db, inp.user_id, s.id)
        await upsert_session(db, s); await db.commit()
        return ChatResponse(session_id=s.id, reply=final_msg, draft=merged,
                            missing=None, final_creation_payload=to_validate)

    # 11) Fallback: ASK with targeted prompt
    fallback = reply_from_llm or _fallback_reply_for_state(state)
    s.last_action = "ASK"
    s.data = {**(s.data or {}), "messages": _append_history(inp.message, fallback)}
    await touch_user_session(db, inp.user_id, s.id)
    await upsert_session(db, s); await db.commit()
    return ChatResponse(session_id=s.id, reply=fallback, draft=merged,
                        missing=missing, final_creation_payload=None)
