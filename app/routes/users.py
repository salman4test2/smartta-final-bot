from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, desc, func
from typing import AsyncGenerator

from ..db import SessionLocal
from ..models import User, UserSession, Session as DBSession
from ..auth import hash_password, verify_password
from ..schemas import (
    UserCreate, UserResponse, UserLogin, 
    UserSessionInfo, UserSessionsResponse, SessionRename
)

router = APIRouter(prefix="/users", tags=["users"])

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as s:
        yield s

@router.post("", response_model=UserResponse)
async def create_user(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    """
    Create a new user with user_id and password.
    Password is automatically hashed using BCrypt for security.
    """
    # Check if user already exists
    result = await db.execute(select(User).where(User.user_id == user_data.user_id))
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")
    
    # Create new user with hashed password
    new_user = User(
        user_id=user_data.user_id,
        password=hash_password(user_data.password)
    )
    
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    
    return UserResponse(
        user_id=new_user.user_id,
        created_at=new_user.created_at.isoformat(),
        updated_at=new_user.updated_at.isoformat()
    )

@router.post("/login")
async def login_user(login_data: UserLogin, db: AsyncSession = Depends(get_db)):
    """
    Authenticate user with user_id and password.
    Returns user info if credentials are valid.
    """
    # Find user
    result = await db.execute(select(User).where(User.user_id == login_data.user_id))
    user = result.scalar_one_or_none()
    
    # Verify user credentials with proper password hashing
    if not user or not verify_password(login_data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    return {
        "user_id": user.user_id,
        "message": "Login successful",
        "created_at": user.created_at.isoformat(),
        "updated_at": user.updated_at.isoformat()
    }

@router.get("/{user_id}/sessions", response_model=UserSessionsResponse)
async def get_user_sessions(user_id: str, db: AsyncSession = Depends(get_db), 
                           limit: int = 50, offset: int = 0):
    """
    Get all sessions created by a specific user, ordered by last activity (newest first).
    Supports pagination with limit and offset parameters.
    """
    # Verify user exists
    user_result = await db.execute(select(User).where(User.user_id == user_id))
    user = user_result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get all user sessions with session details, ordered by session activity
    query = select(
        UserSession.session_id,
        UserSession.session_name,
        UserSession.created_at,
        UserSession.updated_at,
        DBSession.data,
        DBSession.updated_at.label('session_last_activity')
    ).select_from(
        UserSession.__table__.join(DBSession, UserSession.session_id == DBSession.id)
    ).where(
        UserSession.user_id == user_id
    ).order_by(desc(DBSession.updated_at)).limit(limit).offset(offset)
    
    result = await db.execute(query)
    sessions_data = result.fetchall()
    
    # Get total count for pagination
    total_query = select(UserSession).where(UserSession.user_id == user_id)
    total_result = await db.execute(total_query)
    total_sessions = len(total_result.fetchall())
    
    sessions = []
    for session_data in sessions_data:
        # Count messages in session
        messages = session_data.data.get("messages", []) if session_data.data else []
        message_count = len(messages)
        
        sessions.append(UserSessionInfo(
            session_id=session_data.session_id,
            session_name=session_data.session_name,
            created_at=session_data.created_at.isoformat(),
            updated_at=session_data.updated_at.isoformat(),
            message_count=message_count,
            last_activity=session_data.session_last_activity.isoformat() if session_data.session_last_activity else session_data.updated_at.isoformat()
        ))
    
    return UserSessionsResponse(
        user_id=user_id,
        sessions=sessions,
        total_sessions=total_sessions,
        limit=limit,
        offset=offset,
        has_more=len(sessions) == limit and (offset + limit) < total_sessions
    )

@router.put("/{user_id}/sessions/{session_id}/name")
async def update_session_name(user_id: str, session_id: str, 
                              rename_data: SessionRename, 
                              db: AsyncSession = Depends(get_db)):
    """
    Update the name/title of a user session for display purposes.
    Trims whitespace and updates the updated_at timestamp.
    """
    # Find the user session
    result = await db.execute(
        select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.session_id == session_id
        )
    )
    user_session = result.scalar_one_or_none()
    
    if not user_session:
        raise HTTPException(status_code=404, detail="Session not found for this user")
    
    # Trim session name and handle empty strings
    new_name = (rename_data.session_name or "").strip() or None
    
    # Update session name and timestamp
    await db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.session_id == session_id)
        .values(session_name=new_name, updated_at=func.now())
    )
    await db.commit()
    
    return {"message": "Session name updated successfully", "session_name": new_name}
