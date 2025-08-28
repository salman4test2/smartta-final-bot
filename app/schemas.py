from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

# User management schemas
class UserCreate(BaseModel):
    user_id: str
    password: str

class UserResponse(BaseModel):
    user_id: str
    created_at: str
    updated_at: str

class UserLogin(BaseModel):
    user_id: str
    password: str

class UserSessionInfo(BaseModel):
    session_id: str
    session_name: Optional[str] = None
    created_at: str
    updated_at: str
    message_count: int
    last_activity: str

class UserSessionsResponse(BaseModel):
    user_id: str
    sessions: List[UserSessionInfo]
    total_sessions: int

class SessionCreate(BaseModel):
    user_id: Optional[str] = None
    session_name: Optional[str] = None

class SessionCreateResponse(BaseModel):
    session_id: str
    session_name: Optional[str] = None
    user_id: Optional[str] = None

# Chat and session schemas
class ChatInput(BaseModel):
    message: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None  # Add user_id support

class ChatResponse(BaseModel):
    session_id: str
    reply: str
    draft: Dict[str, Any]
    missing: Optional[List[str]] = None
    final_creation_payload: Optional[Dict[str, Any]] = None

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str

class LLMLogEntry(BaseModel):
    timestamp: str
    direction: str  # "request" or "response"
    payload: Dict[str, Any]
    model: Optional[str] = None
    latency_ms: Optional[int] = None

class SessionDebugData(BaseModel):
    session_id: str
    session_info: Dict[str, Any]
    messages: List[ChatMessage]
    current_draft: Dict[str, Any]
    memory: Dict[str, Any]
    llm_logs: List[LLMLogEntry]
    last_action: Optional[str] = None
    updated_at: str

class SessionData(BaseModel):
    session_id: str
    messages: List[ChatMessage]
    draft: Dict[str, Any]
    memory: Dict[str, Any]
    last_action: Optional[str] = None
    updated_at: str
