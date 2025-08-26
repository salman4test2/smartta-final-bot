from __future__ import annotations
from sqlalchemy import String, Text, Integer, TIMESTAMP, func
#from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
#from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column
import uuid
from .db import Base

class Session(Base):
    __tablename__ = "sessions"
    #id: Mapped[str] = mapped_column(PG_UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    #data: Mapped[dict] = mapped_column(JSONB, default=dict)
    #memory: Mapped[dict] = mapped_column(JSONB, default=dict)
    #active_draft_id: Mapped[str | None] = mapped_column(PG_UUID(as_uuid=False), nullable=True)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    memory: Mapped[dict] = mapped_column(JSON, default=dict)
    active_draft_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    last_action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_question_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[str] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

class Draft(Base):
    __tablename__ = "drafts"
    #id: Mapped[str] = mapped_column(PG_UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    #session_id: Mapped[str] = mapped_column(PG_UUID(as_uuid=False), index=True)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    #draft: Mapped[dict] = mapped_column(JSONB, default=dict)
    #finalized_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    draft: Mapped[dict] = mapped_column(JSON, default=dict)
    finalized_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")
    created_at: Mapped[str] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

class LlmLog(Base):
    __tablename__ = "llm_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    #session_id: Mapped[str] = mapped_column(PG_UUID(as_uuid=False), index=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    direction: Mapped[str] = mapped_column(String(16))
    #payload: Mapped[dict] = mapped_column(JSONB)
    payload: Mapped[dict] = mapped_column(JSON)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ts: Mapped[str] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
