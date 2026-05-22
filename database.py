# backend/database.py

import logging
import os
from typing import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
load_dotenv()

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. "
        "Add it to your .env file.\n"
        "Example: postgresql+asyncpg://user:password@localhost:5432/interview_db"
    )

# ---------------------------------------------------------------------------
# Normalize URL scheme
# ---------------------------------------------------------------------------
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

# ---------------------------------------------------------------------------
# Issue 5 — Never log database URL (hides credentials and host info)
# ---------------------------------------------------------------------------
logger.info("Database configuration loaded")

# ---------------------------------------------------------------------------
# Async Engine
# ---------------------------------------------------------------------------
engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("DB_ECHO", "false").lower() == "true",
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
)

# ---------------------------------------------------------------------------
# Async Session Factory
# ---------------------------------------------------------------------------
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# ---------------------------------------------------------------------------
# Declarative Base
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Dependency — get_db
#
# Issue 4 — Single commit point: commit happens ONLY here.
# Routes must NOT call db.commit() themselves.
# Routes call db.flush() if they need IDs before commit.
# ---------------------------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yields an async DB session.

    Transaction rules:
      - Routes use db.flush() to get IDs without committing.
      - ONLY get_db() calls db.commit() at request end.
      - On any exception → rollback automatically.
      - Session always closed in finally block.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()       # Single commit point
        except Exception as e:
            await session.rollback()
            logger.error(f"DB session rolled back due to: {type(e).__name__}")
            raise
        finally:
            await session.close()