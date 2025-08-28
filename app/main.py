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
from .models import Session as DBSession, Draft
from .repo import get_or_create_session, upsert_session, create_draft, log_llm
from .config import get_config, reload_config
from .prompts import build_system_prompt, build_context_block
from .llm import LlmClient
from .validator import validate_schema, lint_rules
from .schemas import ChatInput, ChatResponse, SessionData, ChatMessage, SessionDebugData, LLMLogEntry
from .utils import merge_deep

app = FastAPI(title="LLM-First WhatsApp Template Builder", version="4.0.0")

import hashlib

def _qhash(s: str) -> str:
    return hashlib.sha1((s or "").encode("utf-8")).hexdigest()[:12]

# --- CORS for web UI ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in prod if you have a fixed UI origin
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

    async with engine.begin() as aconn:
        await aconn.run_sync(Base.metadata.create_all)
        try:
            if engine.url.drivername.startswith("sqlite"):
                await aconn.exec_driver_sql("PRAGMA journal_mode=WAL;")
                await aconn.exec_driver_sql("PRAGMA synchronous=NORMAL;")
                await aconn.exec_driver_sql("PRAGMA foreign_keys=ON;")
        except Exception:
            pass

# ---------- Helpers ----------

LANG_MAP = {
    "english": "en_US", "en": "en_US", "en_us": "en_US",
    "hindi": "hi_IN", "hi": "hi_IN", "hi_in": "hi_IN",
    "spanish": "es_MX", "es": "es_MX", "es_mx": "es_MX",
}

def _normalize_language(s: str | None) -> str | None:
    if not s:
        return None
    key = s.strip().lower().replace("-", "_").replace(" ", "")
    return LANG_MAP.get(key, s if "_" in s else None)

def _is_affirmation(text: str) -> bool:
    t = (text or "").strip().lower()
    return any(t == w or t.startswith(w) for w in [
        "yes","y","ok","okay","sure","sounds good","go ahead",
        "please proceed","proceed","confirm","finalize","do it"
    ])

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

def _classify_user_intent(message: str, current_state: str) -> str:
    msg = (message or "").lower()
    if any(w in msg for w in ["marketing", "markting", "promo", "promotion", "offer"]):
        return "category_marketing"
    if any(w in msg for w in ["utility", "transactional", "update", "notification"]):
        return "category_utility"
    if any(w in msg for w in ["auth", "authentication", "otp", "verify", "verification"]):
        return "category_auth"
    if any(w in msg for w in ["english", "en_us", "spanish", "es_mx", "hindi", "hi_in"]):
        return "language_selection"
    if current_state == "need_name" and len(msg.split()) <= 3:
        return "template_name"
    if any(w in msg for w in ["message", "text", "content", "body", "say"]):
        return "content_request"
    if any(w in msg for w in ["done", "finish", "finalize", "complete", "ready", "yes"]):
        return "finalize_request"
    if any(w in msg for w in ["joke", "story", "weather", "hello", "hi", "hey"]):
        return "chitchat"
    return "unclear"

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

    # drop blank strings
    for k in ("name","language","category"):
        if k in c and isinstance(c[k], str) and not c[k].strip():
            c.pop(k, None)

    # components clean
    comps = c.get("components")
    if isinstance(comps, list):
        clean = []
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
                elif fmt in {"IMAGE","VIDEO","DOCUMENT","LOCATION"}:
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
                    b2 = []
                    for b in btns:
                        if not isinstance(b, dict) or "type" not in b or "text" not in b:
                            continue
                        bt = b["type"]
                        if bt == "URL" and not b.get("url"):
                            continue
                        if bt == "PHONE_NUMBER" and not b.get("phone_number"):
                            continue
                        b2.append(b)
                    if b2:
                        clean.append({"type":"BUTTONS","buttons":b2})
        if clean:
            c["components"] = clean
        else:
            c.pop("components", None)
    elif "components" in c:
        c.pop("components", None)
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

def _targeted_missing_reply(missing: List[str]) -> str:
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

@app.get("/health")
async def health():
    cfg = get_config()
    return {"status": "ok", "model": cfg.get("model"), "db": "ok"}

@app.post("/config/reload")
async def config_reload():
    """Reload configuration from disk"""
    cfg = reload_config()
    return {"ok": True, "model": cfg.get("model")}

@app.get("/session/new")
async def new_session(db: AsyncSession = Depends(get_db)):
    s = await get_or_create_session(db, None)
    await db.commit()
    return {"session_id": s.id}

@app.get("/session/{session_id}", response_model=SessionData)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """
    Retrieve session data including chat history for UI integration.
    Returns messages in chronological order for chat UI display.
    """
    s = await get_or_create_session(db, session_id)
    
    # Get current draft
    current_draft = {}
    if s.active_draft_id:
        draft = await db.get(Draft, s.active_draft_id)
        if draft:
            current_draft = draft.draft or {}
    
    # Extract messages
    messages_data = (s.data or {}).get("messages", [])
    messages = [ChatMessage(role=msg["role"], content=msg["content"]) for msg in messages_data]
    
    return SessionData(
        session_id=s.id,
        messages=messages,
        draft=current_draft,
        memory=s.memory or {},
        last_action=s.last_action,
        updated_at=s.updated_at.isoformat() if s.updated_at else ""
    )

@app.get("/session/{session_id}/debug", response_model=SessionDebugData)
async def get_session_debug(session_id: str, db: AsyncSession = Depends(get_db)):
    """
    Debug endpoint: Get complete session data including LLM request/response logs.
    Provides detailed information for troubleshooting and development.
    """
    from sqlalchemy import text
    
    s = await get_or_create_session(db, session_id)
    
    # Get current draft
    current_draft = {}
    if s.active_draft_id:
        draft = await db.get(Draft, s.active_draft_id)
        if draft:
            current_draft = draft.draft or {}
    
    # Extract messages
    messages_data = (s.data or {}).get("messages", [])
    messages = [ChatMessage(role=msg["role"], content=msg["content"]) for msg in messages_data]
    
    # Get LLM logs for this session
    result = await db.execute(text("""
        SELECT direction, payload, model, latency_ms, ts
        FROM llm_logs 
        WHERE session_id = :session_id 
        ORDER BY ts ASC
    """), {"session_id": session_id})
    
    llm_logs = []
    for log in result.fetchall():
        llm_logs.append(LLMLogEntry(
            timestamp=log[4].isoformat() if log[4] else "",
            direction=log[0],
            payload=log[1] or {},
            model=log[2],
            latency_ms=log[3]
        ))
    
    # Session info for debugging
    session_info = {
        "id": s.id,
        "active_draft_id": s.active_draft_id,
        "last_question_hash": s.last_question_hash,
        "created_at": s.updated_at.isoformat() if s.updated_at else "",
        "total_messages": len(messages),
        "total_llm_calls": len(llm_logs)
    }
    
    return SessionDebugData(
        session_id=s.id,
        session_info=session_info,
        messages=messages,
        current_draft=current_draft,
        memory=s.memory or {},
        llm_logs=llm_logs,
        last_action=s.last_action,
        updated_at=s.updated_at.isoformat() if s.updated_at else ""
    )

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
    system = build_system_prompt(cfg)
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
    s.memory = memory

    llm = LlmClient(model=cfg.get("model", "gpt-4o-mini"),
                    temperature=float(cfg.get("temperature", 0.2)))

    try:
        out = llm.respond(system, context, msgs, safe_message)
        out = _validate_llm_response(out)
    except Exception as e:
        await log_llm(db, s.id, "error",
                      {"error": str(e), "user_input": safe_message},
                      cfg.get("model"), None)
        fallback = _fallback_reply_for_state(current_state)
        return ChatResponse(session_id=s.id, reply=fallback,
                            draft=draft, missing=_compute_missing(draft, memory),
                            final_creation_payload=None)

    # logs
    await log_llm(db, s.id, "request",
                  {"system": system, "context": context, "history": msgs,
                   "user": safe_message, "state": current_state, "intent": user_intent},
                  cfg.get("model"), None)
    await log_llm(db, s.id, "response", out, cfg.get("model"), out.get("_latency_ms"))

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
        s.memory = memory

    # local history helper
    def _append_history(user_text: str, assistant_text: str) -> List[Dict[str, str]]:
        new_hist = msgs + [{"role": "user", "content": user_text},
                           {"role": "assistant", "content": assistant_text}]
        return new_hist[-max_turns:]

    # 4) Let LLM drive category; don't inject server question
    category = (candidate.get("category") or memory.get("category") or draft.get("category"))
    if category and not memory.get("category"):
        s.memory = merge_deep(memory, {"category": category})

    # 5) Non-FINAL → merge sanitized candidate (with extras auto-apply on "yes")
    if action in {"ASK","DRAFT","UPDATE","CHITCHAT"}:
        candidate = _auto_apply_extras_on_yes(safe_message, candidate, memory)
        cand_clean = _sanitize_candidate(candidate) if candidate else {}
        merged = merge_deep(draft, cand_clean) if cand_clean else draft

        # if language still missing, try to normalize from user text like "english"
        if not merged.get("language"):
            lang_guess = _normalize_language(safe_message)
            if lang_guess:
                merged["language"] = lang_guess

        d.draft = merged
        s.last_action = action

        # Trust LLM's missing calculation, but supplement with any obvious gaps
        llm_missing = out.get("missing") or []
        computed_missing = _compute_missing(merged, memory)
        
        # Use LLM missing as primary, only add computed missing if LLM missed something obvious
        missing = llm_missing[:]
        for item in computed_missing:
            if item not in missing and item in ["category", "language", "name", "body"]:
                missing.append(item)
        
        final_reply = reply or _targeted_missing_reply(missing)

        s.data = {**(s.data or {}), "messages": _append_history(inp.message, final_reply)}
        await upsert_session(db, s); await db.commit()

        return ChatResponse(session_id=s.id, reply=final_reply,
                            draft=merged, missing=missing, final_creation_payload=None)

    # 6) FINAL → sanitize -> validate -> persist (also enforce requested extras)
    if action == "FINAL":
        candidate = _auto_apply_extras_on_yes(safe_message, candidate, memory)
        cand_clean = _sanitize_candidate(candidate) if candidate else {}
        candidate = cand_clean or draft or _minimal_scaffold(memory)

        # enforce extras if user asked for them but they are still missing
        def _has_component_kind(p: Dict[str, Any], kind: str) -> bool:
            return any(
                isinstance(c, dict) and (c.get("type") or "").upper() == kind
                for c in (p.get("components") or [])
            )

        missing_extras = []
        if memory.get("wants_header") and not _has_component_kind(candidate, "HEADER"):
            missing_extras.append("header")
        if memory.get("wants_footer") and not _has_component_kind(candidate, "FOOTER"):
            missing_extras.append("footer")
        if memory.get("wants_buttons") and not _has_component_kind(candidate, "BUTTONS"):
            missing_extras.append("buttons")

        if missing_extras:
            # ask a single targeted question rather than finalize
            d.draft = merge_deep(draft, candidate)
            s.last_action = "ASK"
            ask = _targeted_missing_reply(missing_extras)
            s.data = {**(s.data or {}), "messages": _append_history(inp.message, ask)}
            await upsert_session(db, s); await db.commit()
            return ChatResponse(
                session_id=s.id,
                reply=ask,
                draft=d.draft,
                missing=_compute_missing(d.draft, memory),
                final_creation_payload=None
            )

        schema = cfg.get("creation_payload_schema", {}) or {}
        issues = validate_schema(candidate, schema)
        issues += lint_rules(candidate, cfg.get("lint_rules", {}) or {})

        if issues:
            d.draft = merge_deep(draft, candidate)
            s.last_action = "ASK"
            final_reply = (reply + ("\n\nPlease fix: " + "; ".join(issues) if issues else "")).strip()
            s.data = {**(s.data or {}), "messages": _append_history(inp.message, final_reply)}
            await upsert_session(db, s); await db.commit()
            return ChatResponse(session_id=s.id, reply=final_reply, draft=d.draft,
                                missing=_compute_missing(d.draft, memory) + ["fix_validation_issues"],
                                final_creation_payload=None)

        d.finalized_payload = candidate
        d.status = "FINAL"
        d.draft = candidate
        s.last_action = "FINAL"
        s.data = {**(s.data or {}), "messages": _append_history(inp.message, reply or "Finalized.")}
        await upsert_session(db, s); await db.commit()
        return ChatResponse(session_id=s.id, reply=reply or "Finalized.",
                            draft=d.draft, missing=None, final_creation_payload=candidate)

    # 7) Fallback (treat as ASK)
    final_draft = candidate or draft
    d.draft = final_draft
    s.last_action = "ASK"
    missing = _compute_missing(final_draft, memory)
    final_reply = reply or _targeted_missing_reply(missing)
    if final_reply.endswith("?"):
        qh = _qhash(final_reply)
        if s.last_question_hash == qh and _is_affirmation(safe_message):
            # auto-apply extras and try to fill a single missing slot
            merged = merge_deep(merged, _auto_apply_extras_on_yes(safe_message, {}, memory))
            if "language" in missing:
                guess = _normalize_language(safe_message) or memory.get("language_pref") or "en_US"
                merged["language"] = guess
            if "name" in missing and ("you choose" in safe_message.lower() or "suggest" in safe_message.lower()):
                merged["name"] = _slug(memory.get("event_label") or "template")
            if "body" in missing and "you choose" in safe_message.lower():
                # keep it short & compliant; the LLM will refine next turn
                merged.setdefault("components", []).insert(0, {"type": "BODY", "text": "Hi {{1}}, we have a special offer for you!"})
            d.draft = merged
            final_reply = _targeted_missing_reply(_compute_missing(merged, memory))
        # store hash (or clear if not a question)
        s.last_question_hash = qh
    else:
        s.last_question_hash = None # not a question      
    s.data = {**(s.data or {}), "messages": _append_history(inp.message, final_reply)}
    await upsert_session(db, s); await db.commit()
    return ChatResponse(session_id=s.id, reply=final_reply,
                        draft=final_draft, missing=missing,
                        final_creation_payload=None)
