from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()  # load .env BEFORE reading env vars

import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "").strip() or "sqlite+aiosqlite:///./data/watemp.db"

# Handle different database configurations
if DATABASE_URL.startswith("sqlite"):
    Path("./data").mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(
        DATABASE_URL, 
        echo=False, 
        pool_pre_ping=True
    )
elif DATABASE_URL.startswith("postgresql"):
    # Neon PostgreSQL with psycopg async driver
    # Best practices for Neon: connection pooling with simplified settings
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_size=10,          # Recommended for Neon
        max_overflow=20,       # Allow burst connections
        pool_pre_ping=True,    # Validate connections
        pool_recycle=300,      # Recycle connections every 5 minutes
    )
else:
    engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()