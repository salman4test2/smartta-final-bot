from __future__ import annotations
import uuid
from datetime import datetime

from sqlalchemy import (
    String, Integer, DateTime, func, JSON, ForeignKey, CheckConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class User(Base):
    __tablename__ = "users"

    # UUID-as-string for user ID
    user_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Password - in production, this should be hashed
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UserSession(Base):
    __tablename__ = "user_sessions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign key to users table
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    
    # Foreign key to sessions table
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    # Optional session name/title for display
    session_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Session(Base):
    __tablename__ = "sessions"

    # UUID-as-string keeps it portable across SQLite and Postgres
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Store chat history / ui state
    data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # Store memory (facts/preferences extracted by LLM)
    memory: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Active draft pointer
    active_draft_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    last_action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_question_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Portable timestamp; client onupdate works across SQLite/Postgres
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Keep referential integrity (works on SQLite with PRAGMA foreign_keys=ON)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Evolving working copy
    draft: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # Set only when finalized
    finalized_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    status: Mapped[str] = mapped_column(String(16), default="DRAFT", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("status in ('DRAFT','FINAL')", name="ck_drafts_status"),
    )


class LlmLog(Base):
    __tablename__ = "llm_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    direction: Mapped[str] = mapped_column(String(16), nullable=False)  # "request" | "response" | "error"
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


# Helpful indexes (portable)
Index("ix_sessions_updated_at", Session.updated_at)
Index("ix_drafts_session_created_at", Draft.session_id, Draft.created_at)
Index("ix_llm_logs_session_ts", LlmLog.session_id, LlmLog.ts)
Index("ix_user_sessions_user_id", UserSession.user_id)
Index("ix_user_sessions_updated_at", UserSession.updated_at)
Index("ix_user_sessions_user_id", UserSession.user_id)
Index("ix_user_sessions_session_id", UserSession.session_id)
