from __future__ import annotations
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from .models import Session, Draft, LlmLog, UserBusinessProfile

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

async def ensure_user_exists(db: AsyncSession, user_id: str):
    """Ensure a user exists, creating one if it doesn't"""
    from sqlalchemy import select
    from .models import User
    
    # Check if user exists
    result = await db.execute(select(User).where(User.user_id == user_id))
    existing_user = result.scalar_one_or_none()
    
    if not existing_user:
        # Create user with a default password (in production this should be handled properly)
        new_user = User(user_id=user_id, password="default")
        db.add(new_user)
        await db.flush()

async def upsert_user_session(db: AsyncSession, user_id: str, session_id: str, session_name: str = None):
    """Create or update a user session association"""
    from sqlalchemy import select, update, func
    from .models import UserSession
    
    # Ensure user exists first
    await ensure_user_exists(db, user_id)
    
    # Check if user session association already exists
    result = await db.execute(
        select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.session_id == session_id
        )
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        # Update existing if session_name is provided
        if session_name is not None:
            await db.execute(
                update(UserSession)
                .where(UserSession.user_id == user_id, UserSession.session_id == session_id)
                .values(session_name=session_name, updated_at=func.now())
            )
    else:
        # Create new
        user_session = UserSession(
            user_id=user_id,
            session_id=session_id,
            session_name=session_name
        )
        db.add(user_session)

async def touch_user_session(db: AsyncSession, user_id: str, session_id: str):
    """Update user session timestamp when user sends a message"""
    if not user_id:
        return
        
    from sqlalchemy import select, update, func
    from .models import UserSession
    
    # Ensure user exists first
    await ensure_user_exists(db, user_id)
    
    # Check if user session association exists
    user_session_result = await db.execute(
        select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.session_id == session_id
        )
    )
    user_session = user_session_result.scalar_one_or_none()
    
    if user_session:
        # Update the user session timestamp
        await db.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.session_id == session_id)
            .values(updated_at=func.now())
        )
    else:
        # Create new user session association if it doesn't exist
        new_user_session = UserSession(
            user_id=user_id,
            session_id=session_id,
            session_name=None
        )
        db.add(new_user_session)

async def get_user_business_profile(db: AsyncSession, user_id: str) -> Optional[UserBusinessProfile]:
    """Get user's business profile"""
    from sqlalchemy import select
    
    result = await db.execute(
        select(UserBusinessProfile).where(UserBusinessProfile.user_id == user_id)
    )
    return result.scalar_one_or_none()

async def upsert_user_business_profile(db: AsyncSession, user_id: str, profile_data: Dict[str, Any]) -> UserBusinessProfile:
    """Create or update user's business profile"""
    from sqlalchemy import select
    
    # Check if profile exists
    result = await db.execute(
        select(UserBusinessProfile).where(UserBusinessProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    
    if profile:
        # Update existing profile
        for key, value in profile_data.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
    else:
        # Create new profile
        profile = UserBusinessProfile(user_id=user_id, **profile_data)
        db.add(profile)
    
    await db.flush()
    return profile
