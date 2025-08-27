from __future__ import annotations
from typing import Dict, Any, List
from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import os

from .db import engine, SessionLocal, Base
from .models import Session as DBSession, Draft
from .repo import get_or_create_session, upsert_session, create_draft, log_llm
from .config import get_config
from .prompts import build_system_prompt, build_context_block
from .llm import LlmClient
from .validator import validate_schema, lint_rules
from .schemas import ChatInput, ChatResponse
from .utils import merge_deep
from difflib import get_close_matches

app = FastAPI(title="LLM-First WhatsApp Template Builder", version="4.0.0")

async def get_db() -> AsyncSession:
    async with SessionLocal() as s:
        yield s

# in app/main.py startup() after imports
from sqlalchemy.engine.url import make_url
import os

@app.on_event("startup")
async def on_startup():
    # (optional) log which DB you actually picked up
    try:
        safe = make_url(os.getenv("DATABASE_URL", "")).set(password="***")
        print(f"[DEBUG] FastAPI startup: DATABASE_URL={safe}")
    except Exception:
        pass

    async with engine.begin() as aconn:
        # create tables
        await aconn.run_sync(Base.metadata.create_all)

        # SQLite PRAGMAs (no-ops on Postgres)
        try:
            if engine.url.drivername.startswith("sqlite"):
                await aconn.exec_driver_sql("PRAGMA journal_mode=WAL;")
                await aconn.exec_driver_sql("PRAGMA synchronous=NORMAL;")
                await aconn.exec_driver_sql("PRAGMA foreign_keys=ON;")
        except Exception:
            pass

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
    LLM-first orchestration:
    - No hardcoded category/occasion/button logic in server.
    - LLM must infer category, fields, and ask one concise question if ambiguous.
    - Server merges memory/draft, validates on FINAL, and always returns a non-empty draft.
    - Minimal scaffold is used only when LLM omitted a draft; scaffold uses LLM memory (open vocabulary).
    """
    cfg = get_config()
    hist_cfg = cfg.get("history", {}) or {}
    max_turns = int(hist_cfg.get("max_turns", 200))

    # ------------------- 1) Load/create session + draft -------------------
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

    # ------------------- 2) Build LLM inputs + call -------------------
    system = build_system_prompt(cfg)
    context = build_context_block(draft, memory, cfg)

    llm = LlmClient(
        model=cfg.get("model", "gpt-4.1-mini"),
        temperature=float(cfg.get("temperature", 0.2))
    )
    out = llm.respond(system, context, msgs, inp.message)

    # Logs (request/response)
    await log_llm(
        db, s.id, "request",
        {"system": system, "context": context, "history": msgs, "user": inp.message},
        cfg.get("model"), None
    )
    await log_llm(
        db, s.id, "response",
        out, cfg.get("model"), out.get("_latency_ms")
    )

    # ------------------- 3) Extract LLM outputs -------------------
    action = str(out.get("agent_action") or "ASK").upper()
    reply = (out.get("message_to_user") or "").strip()
    candidate = out.get("final_creation_payload") or out.get("draft") or {}
    mem_update = out.get("memory") or {}

    # Merge memory (LLM owns all open-vocabulary discovery: category, event, language, buttons, etc.)
    if mem_update:
        memory = merge_deep(memory, mem_update)
        s.memory = memory

    # ------------------- 4) Helpers (minimal & generic) -------------------
    import re, datetime as dt

    def _append_history(user_text: str, assistant_text: str) -> List[Dict[str, str]]:
        new_hist = msgs + [{"role": "user", "content": user_text},
                           {"role": "assistant", "content": assistant_text}]
        return new_hist[-max_turns:]

    def _slug(s_: str) -> str:
        s_ = (s_ or "").lower().strip()
        s_ = re.sub(r"[^a-z0-9_]+", "_", s_)
        return re.sub(r"_+", "_", s_).strip("_") or "template"

    def _minimal_scaffold(mem: Dict[str, Any]) -> Dict[str, Any]:
        """
        Only used when the LLM did not provide a draft.
        Uses LLM memory (category/event/business/language/buttons) to create a tiny, compliant draft.
        No hardcoded occasion/button logic here; open vocabulary is taken from memory.
        """
        cat = (mem.get("category") or "").upper()
        if cat not in {"MARKETING", "UTILITY", "AUTHENTICATION"}:
            # Category unknown → ask once and return empty scaffold; caller handles the question.
            return {}

        lang = mem.get("language_pref") or mem.get("language") or "en_US"
        event = mem.get("event_label") or mem.get("event") or "offer"
        business = mem.get("business_type") or mem.get("business") or "brand"

        name = mem.get("proposed_name") or f"{_slug(event)}_{_slug(business)}_v{dt.datetime.utcnow().strftime('%m%d')}"
        components: List[Dict[str, Any]] = []

        if cat == "AUTHENTICATION":
            body = "{{1}} is your verification code. For your security, do not share this code. This code expires in {{2}} minutes."
            components.append({"type": "BODY", "text": body})
            return {"category": cat, "language": lang, "name": name, "components": components}

        if cat == "UTILITY":
            body = "Hello {{1}}, your {{2}} has been updated. Latest status: {{3}}."
        else:  # MARKETING
            body = f"Hi {{1}}, {event}! Enjoy {{2}}."

        components.append({"type": "BODY", "text": body})

        # Buttons only if the LLM memory explicitly asks for them (open vocabulary, no server logic)
        btn_req = mem.get("buttons_request") or {}
        try:
            cnt = int(btn_req.get("count") or 0)
        except Exception:
            cnt = 0
        types = [t for t in (btn_req.get("types") or []) if isinstance(t, str)]

        if cnt > 0:
            # Provide neutral placeholders so schema passes; real labels should come from the LLM next turn
            buttons: List[Dict[str, Any]] = []
            # honor requested types order (if any), otherwise default to QUICK_REPLYs
            type_cycle = types if types else ["QUICK_REPLY"]
            i = 0
            while i < cnt:
                t = type_cycle[min(i, len(type_cycle)-1)]
                if t == "URL":
                    buttons.append({"type": "URL", "text": "Open Link", "url": "https://example.com"})
                elif t == "PHONE_NUMBER":
                    buttons.append({"type": "PHONE_NUMBER", "text": "Call Us", "phone_number": "+10000000000"})
                else:
                    buttons.append({"type": "QUICK_REPLY", "text": f"Option {i+1}", "payload": f"OPTION_{i+1}"})
                i += 1
            components.append({"type": "BUTTONS", "buttons": buttons})

        return {"category": cat, "language": lang, "name": name, "components": components}

    def _compute_missing(p: Dict[str, Any]) -> List[str]:
        miss: List[str] = []
        if not p.get("category"):
            miss.append("category")
        if not p.get("name"):
            miss.append("name")
        if not p.get("language"):
            miss.append("language")
        comps = p.get("components") or []
        has_body = any(isinstance(c, dict) and c.get("type") == "BODY" and (c.get("text") or "").strip() for c in comps)
        if not has_body:
            miss.append("body")
        return miss

    # ------------------- 5) Category gate (LLM-led) -------------------
    category = (candidate.get("category")
                or memory.get("category"))  # LLM is responsible for setting this

    if not category:
        # One concise question; no extra logic. LLM must decide category next turn.
        q = "Which template category should I use — MARKETING, UTILITY, or AUTHENTICATION?"
        s.last_action = "ASK"
        s.data = {**(s.data or {}), "messages": _append_history(inp.message, q)}
        await upsert_session(db, s); await db.commit()
        return ChatResponse(session_id=s.id, reply=q, draft=draft, missing=["category"], final_creation_payload=None)

    # ------------------- 6) Non-FINAL: always return a draft -------------------
    if action in {"ASK", "DRAFT", "UPDATE", "CHITCHAT"}:
        # Only merge if LLM actually provided a valid candidate
        if candidate:
            # Validate candidate before merging to prevent malformed data
            if isinstance(candidate, dict):
                # Don't accept empty components array or empty language
                if "components" in candidate and candidate["components"] == []:
                    candidate.pop("components", None)
                if "language" in candidate and not candidate["language"]:
                    candidate.pop("language", None)
                merged = merge_deep(draft, candidate)
            else:
                merged = draft
        else:
            merged = draft  # Keep existing draft, don't create dummy content

        # Persist
        d.draft = merged
        s.last_action = action
        s.data = {**(s.data or {}), "messages": _append_history(inp.message, reply or "What would you like me to help you create?")}
        await upsert_session(db, s); await db.commit()

        missing = out.get("missing") or _compute_missing(merged)
        return ChatResponse(
            session_id=s.id,
            reply=reply or "What would you like me to help you create?",
            draft=merged,
            missing=missing,
            final_creation_payload=None,
        )

    # ------------------- 7) FINAL: validate schema + lint (policy from config only) -------------------
    if action == "FINAL":
        candidate = candidate or draft or _minimal_scaffold(memory)

        schema = cfg.get("creation_payload_schema", {}) or {}
        issues = validate_schema(candidate, schema)
        issues += lint_rules(candidate, cfg.get("lint_rules", {}) or {})

        if issues:
            d.draft = merge_deep(draft, candidate)
            s.last_action = "ASK"
            final_reply = (reply + ("\n\nPlease fix: " + "; ".join(issues) if issues else "")).strip()
            s.data = {**(s.data or {}), "messages": _append_history(inp.message, final_reply)}
            await upsert_session(db, s); await db.commit()
            return ChatResponse(
                session_id=s.id,
                reply=final_reply,
                draft=d.draft,
                missing=(out.get("missing") or []) + ["fix_validation_issues"],
                final_creation_payload=None,
            )

        # Valid → finalize
        d.finalized_payload = candidate
        d.status = "FINAL"
        d.draft = candidate
        s.last_action = "FINAL"
        s.data = {**(s.data or {}), "messages": _append_history(inp.message, reply or "Finalized.")}
        await upsert_session(db, s); await db.commit()
        return ChatResponse(
            session_id=s.id,
            reply=reply or "Finalized.",
            draft=d.draft,
            missing=None,
            final_creation_payload=candidate,
        )

    # ------------------- 8) Fallback: behave like ASK with scaffold -------------------
    # Only scaffold if we have enough information and current draft is empty
    if not candidate and not draft and memory.get("category"):
        candidate = _minimal_scaffold(memory)

    final_draft = candidate or draft
    d.draft = final_draft
    s.last_action = "ASK"
    s.data = {**(s.data or {}), "messages": _append_history(inp.message, reply or "What would you like me to help you create?")}
    await upsert_session(db, s); await db.commit()
    return ChatResponse(
        session_id=s.id,
        reply=reply or "What would you like me to help you create?",
        draft=final_draft,
        missing=_compute_missing(final_draft),
        final_creation_payload=None,
    )
