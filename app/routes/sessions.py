from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..db import SessionLocal
from ..models import User, UserSession, Draft, Session as DBSession
from ..repo import get_or_create_session, upsert_user_session
from ..schemas import SessionCreate, SessionCreateResponse, SessionData, ChatMessage

router = APIRouter(prefix="/session", tags=["sessions"])

async def get_db() -> AsyncSession:
    async with SessionLocal() as s:
        yield s

@router.post("/new", response_model=SessionCreateResponse)
async def new_session_post(session_data: SessionCreate, db: AsyncSession = Depends(get_db)):
    """
    Create a new session with optional name and user association.
    Allows users to provide a meaningful name like 'Diwali Template Creation'.
    """
    s = await get_or_create_session(db, None)
    
    session_name = session_data.session_name
    user_id = session_data.user_id
    
    # If user_id is provided, create user session association
    if user_id:
        # Verify user exists
        user_result = await db.execute(select(User).where(User.user_id == user_id))
        user = user_result.scalar_one_or_none()
        
        if user:
            # Create user session association with the provided name using upsert
            await upsert_user_session(db, user_id, s.id, session_name)
    
    await db.commit()
    return SessionCreateResponse(
        session_id=s.id,
        session_name=session_name,
        user_id=user_id
    )

@router.get("/new")
async def new_session_get(user_id: str = None, db: AsyncSession = Depends(get_db)):
    """
    Create a new session (GET method for backward compatibility).
    If user_id is provided, the session will be linked to that user.
    """
    s = await get_or_create_session(db, None)
    
    # If user_id is provided, create user session association
    if user_id:
        # Verify user exists
        user_result = await db.execute(select(User).where(User.user_id == user_id))
        user = user_result.scalar_one_or_none()
        
        if user:
            # Create user session association using upsert
            await upsert_user_session(db, user_id, s.id, None)
    
    await db.commit()
    return {"session_id": s.id}

@router.get("/{session_id}", response_model=SessionData)
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
