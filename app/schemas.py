from __future__ import annotations
from typing import Any, Dict, List, Optional, Annotated, Literal
from pydantic import BaseModel, Field, ConfigDict

# Base configuration for all models
class BaseModelWithConfig(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

# User management schemas
class UserCreate(BaseModelWithConfig):
    user_id: Annotated[str, Field(min_length=1, max_length=50)]
    password: Annotated[str, Field(min_length=8, max_length=128)]

class UserResponse(BaseModelWithConfig):
    user_id: str
    created_at: str
    updated_at: str

class UserLogin(BaseModelWithConfig):
    user_id: Annotated[str, Field(min_length=1, max_length=50)]
    password: Annotated[str, Field(min_length=1, max_length=128)]

class UserSessionInfo(BaseModelWithConfig):
    session_id: str
    session_name: Optional[Annotated[str, Field(min_length=1, max_length=120)]] = None
    created_at: str
    updated_at: str
    message_count: int
    last_activity: str

class UserSessionsResponse(BaseModelWithConfig):
    user_id: str
    sessions: List[UserSessionInfo]
    total_sessions: int
    limit: int
    offset: int
    has_more: bool

class SessionCreate(BaseModelWithConfig):
    user_id: Optional[Annotated[str, Field(min_length=1, max_length=50)]] = None
    session_name: Optional[Annotated[str, Field(
        min_length=1,
        max_length=120,
        description="Optional display name for the session shown in the UI."
    )]] = None

class SessionCreateResponse(BaseModelWithConfig):
    session_id: str
    session_name: Optional[Annotated[str, Field(min_length=1, max_length=120)]] = None
    user_id: Optional[str] = None

class SessionRename(BaseModelWithConfig):
    session_name: Annotated[str, Field(min_length=1, max_length=120)]

# Chat and session schemas
class ChatInput(BaseModelWithConfig):
    message: Annotated[str, Field(min_length=1, max_length=2000)]
    session_id: Optional[str] = None
    user_id: Optional[str] = None  # Add user_id support

class ChatResponse(BaseModelWithConfig):
    session_id: str
    reply: str
    draft: Dict[str, Any]
    missing: Optional[List[str]] = None
    final_creation_payload: Optional[Dict[str, Any]] = None

class ChatMessage(BaseModelWithConfig):
    role: Literal["user", "assistant"]
    content: Annotated[str, Field(min_length=1, max_length=10000)]

class LLMLogEntry(BaseModelWithConfig):
    timestamp: str
    direction: str  # "request" or "response"
    payload: Dict[str, Any]
    model: Optional[str] = None
    latency_ms: Optional[int] = None

class SessionDebugData(BaseModelWithConfig):
    session_id: str
    session_info: Dict[str, Any]
    messages: List[ChatMessage]
    current_draft: Dict[str, Any]
    memory: Dict[str, Any]
    llm_logs: List[LLMLogEntry]
    last_action: Optional[str] = None
    updated_at: str

class SessionData(BaseModelWithConfig):
    session_id: str
    messages: List[ChatMessage]
    draft: Dict[str, Any]
    memory: Dict[str, Any]
    last_action: Optional[str] = None
    updated_at: str

# Additional response schemas for consistency
class SessionInfoResponse(BaseModelWithConfig):
    """Standard response for session information"""
    session_id: str
    session_name: Optional[Annotated[str, Field(min_length=1, max_length=120)]] = None
    user_id: Optional[str] = None
    created_at: str
    updated_at: str
    message_count: int

class ErrorResponse(BaseModelWithConfig):
    """Standard error response format"""
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None

class SuccessResponse(BaseModelWithConfig):
    """Standard success response format"""
    success: bool = True
    message: Optional[str] = None
