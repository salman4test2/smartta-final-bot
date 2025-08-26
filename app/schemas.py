from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

class ChatInput(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    session_id: str
    reply: str
    draft: Dict[str, Any]
    missing: Optional[List[str]] = None
    final_creation_payload: Optional[Dict[str, Any]] = None
