from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()  # load .env BEFORE reading env vars

import os, ssl
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from sqlalchemy.engine.url import make_url
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "").strip() or "sqlite+aiosqlite:///./data/watemp.db"
url = make_url(DATABASE_URL)
if url.drivername.startswith("sqlite"):
    Path("./data").mkdir(parents=True, exist_ok=True)
engine = create_async_engine(str(url), echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()