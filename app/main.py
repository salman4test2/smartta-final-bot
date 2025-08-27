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
from .config import get_config
from .prompts import build_system_prompt, build_context_block
from .llm import LlmClient
from .validator import validate_schema, lint_rules
from .schemas import ChatInput, ChatResponse
from .utils import merge_deep

app = FastAPI(title="LLM-First WhatsApp Template Builder", version="4.0.0")

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

# ---------- Helpers (module-level so they exist before use) ----------

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
    has_body = any(c.get("type") == "BODY" and (c.get("text") or "").strip()
                   for c in (draft.get("components") or []))
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

    if response["agent_action"] == "FINAL":
        draft = response.get("final_creation_payload") or response.get("draft") or {}
        required = ["name","language","category","components"]
        if not all(draft.get(k) for k in required):
            response["agent_action"] = "ASK"
            response["message_to_user"] = "I need a bit more information before finalizing."
    return response

def _sanitize_candidate(cand: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(cand, dict):
        return {}
    c = dict(cand)
    for k in ("name","language","category"):
        if k in c and isinstance(c[k], str) and not c[k].strip():
            c.pop(k, None)
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

                # If model gave header text but omitted format, default to TEXT
                if not fmt and txt:
                    fmt = "TEXT"

                if fmt == "TEXT" and txt:
                    clean.append({"type": "HEADER", "format": "TEXT", "text": txt})
                elif fmt in {"IMAGE", "VIDEO", "DOCUMENT", "LOCATION"}:
                    # keep media/location slot even without example; preview can show placeholder
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

    # If user explicitly asked for extras, require them before FINAL
    if memory.get("wants_header") and not _has_component(p, "HEADER"):
        miss.append("header")
    if memory.get("wants_footer") and not _has_component(p, "FOOTER"):
        miss.append("footer")
    if memory.get("wants_buttons") and not _has_component(p, "BUTTONS"):
        miss.append("buttons")
    return miss

def _slug(s_: str) -> str:
    s_ = (s_ or "").lower().strip()
    s_ = re.sub(r"[^a-z0-9_]+", "_", s_)
    return re.sub(r"_+", "_", s_).strip("_") or "template"

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

def _has_extras_components(p: Dict[str, Any]) -> bool:
    comps = (p or {}).get("components") or []
    return any(isinstance(c, dict) and c.get("type") in {"HEADER","FOOTER","BUTTONS"} for c in comps)

def _user_declined_extras(msg: str) -> bool:
    t = (msg or "").lower()
    return any(phrase in t for phrase in [
        "skip", "no buttons", "no header", "no footer",
        "finalize as is", "looks good as is", "no extras"
    ])

# ---------- Endpoints ----------

@app.get("/health")
async def health():
    cfg = get_config()
    return {"status": "ok", "model": cfg.get("model"), "db": "ok"}

@app.get("/session/new")
async def new_session(db: AsyncSession = Depends(get_db)):
    s = await get_or_create_session(db, None)
    await db.commit()
    return {"session_id": s.id}

@app.post("/chat", response_model=ChatResponse)
async def chat(inp: ChatInput, db: AsyncSession = Depends(get_db)):
    """
    Production-ready WhatsApp Template Builder with comprehensive error handling.
    """
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
    # Track explicit requests so we can block FINAL until they exist
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
                            draft=draft, missing=_compute_missing(draft),
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

    # local helpers
    def _append_history(user_text: str, assistant_text: str) -> List[Dict[str, str]]:
        new_hist = msgs + [{"role": "user", "content": user_text},
                           {"role": "assistant", "content": assistant_text}]
        return new_hist[-max_turns:]

    # ------------------- 5) Let the LLM drive category inference -------------------
    category = (candidate.get("category") or memory.get("category") or draft.get("category"))
    if category and not memory.get("category"):
        s.memory = merge_deep(memory, {"category": category})

    # If category is still absent, DO NOT inject a server-side category question.
    # Trust the LLM's reply to either ask one clarifying question or to infer on its own.
    # We simply continue to the action handling below.

    # 6) Non-FINAL → merge sanitized candidate
    if action in {"ASK","DRAFT","UPDATE","CHITCHAT"}:
        cand_clean = _sanitize_candidate(candidate) if candidate else {}
        merged = merge_deep(draft, cand_clean) if cand_clean else draft

        d.draft = merged
        s.last_action = action
        s.data = {**(s.data or {}), "messages": _append_history(inp.message, reply or "What should I add next?")}
        await upsert_session(db, s); await db.commit()

        missing = out.get("missing") or _compute_missing(merged, memory)
        return ChatResponse(session_id=s.id, reply=reply or "What should I add next?",
                            draft=merged, missing=missing, final_creation_payload=None)

    # 7) FINAL → sanitize -> validate -> persist
    if action == "FINAL":
        cand_clean = _sanitize_candidate(candidate) if candidate else {}
        candidate = cand_clean or draft or _minimal_scaffold(memory)

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
            d.draft = merge_deep(draft, candidate)
            s.last_action = "ASK"
            ask = "You asked for {}. Should I add them now? For header, I can add a TEXT header like “Festive offer just for you!” (≤60 chars).".format(
                ", ".join(missing_extras)
            )
            s.data = {**(s.data or {}), "messages": _append_history(inp.message, ask)}
            await upsert_session(db, s);
            await db.commit()
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
                                missing=(out.get("missing") or []) + ["fix_validation_issues"],
                                final_creation_payload=None)

        d.finalized_payload = candidate
        d.status = "FINAL"
        d.draft = candidate
        s.last_action = "FINAL"
        s.data = {**(s.data or {}), "messages": _append_history(inp.message, reply or "Finalized.")}
        await upsert_session(db, s); await db.commit()
        return ChatResponse(session_id=s.id, reply=reply or "Finalized.",
                            draft=d.draft, missing=None, final_creation_payload=candidate)

    # 8) Fallback (treat as ASK)
    final_draft = candidate or draft
    d.draft = final_draft
    s.last_action = "ASK"
    s.data = {**(s.data or {}), "messages": _append_history(inp.message, reply or "What would you like me to help you create?")}
    await upsert_session(db, s); await db.commit()
    return ChatResponse(session_id=s.id, reply=reply or "What would you like me to help you create?",
                        draft=final_draft, missing = _compute_missing(final_draft, memory),
                        final_creation_payload=None)
