from __future__ import annotations
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from .models import Session, Draft, LlmLog

async def get_or_create_session(db: AsyncSession, sid: Optional[str]) -> Session:
    if sid:
        row = await db.get(Session, sid)
        if row:
            return row
    s = Session(id=sid) if sid else Session()
    db.add(s)
    await db.flush()
    return s

async def upsert_session(db: AsyncSession, s: Session, **kw) -> Session:
    for k, v in kw.items():
        setattr(s, k, v)
    await db.flush()
    return s

async def create_draft(db: AsyncSession, session_id: str, draft: Dict[str, Any], version: int = 1) -> Draft:
    d = Draft(session_id=session_id, version=version, draft=draft)
    db.add(d)
    await db.flush()
    return d

async def update_draft(db: AsyncSession, draft_id: str, patch: Dict[str, Any]) -> Draft:
    d = await db.get(Draft, draft_id)
    for k, v in patch.items():
        setattr(d, k, v)
    await db.flush()
    return d

async def log_llm(db: AsyncSession, session_id: str, direction: str, payload: Dict[str, Any], model: str | None, latency_ms: int | None) -> None:
    db.add(LlmLog(session_id=session_id, direction=direction, payload=payload, model=model, latency_ms=latency_ms))
    await db.flush()
