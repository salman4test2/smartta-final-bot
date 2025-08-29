from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from ..db import SessionLocal
from ..models import Draft
from ..repo import get_or_create_session
from ..schemas import SessionDebugData, ChatMessage, LLMLogEntry

router = APIRouter(prefix="/session", tags=["debug"])

async def get_db() -> AsyncSession:
    async with SessionLocal() as s:
        yield s

@router.get("/{session_id}/debug", response_model=SessionDebugData)
async def get_session_debug(session_id: str, db: AsyncSession = Depends(get_db)):
    """
    Debug endpoint: Get complete session data including LLM request/response logs.
    Provides detailed information for troubleshooting and development.
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
        "updated_at": s.updated_at.isoformat() if s.updated_at else "",
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
