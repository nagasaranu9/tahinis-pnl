import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

# Workers call asyncio.run() per task — each call creates a new event loop,
# so pooled connections bound to the previous loop cause "attached to different loop" errors.
# NullPool creates a fresh connection per session and closes it immediately, avoiding this.
_in_worker = os.environ.get("CELERY_WORKER_RUNNING") == "true"

engine = create_async_engine(
    str(settings.DATABASE_URL),
    **({
        "poolclass": NullPool,
    } if _in_worker else {
        "pool_size": settings.DATABASE_POOL_SIZE,
        "max_overflow": settings.DATABASE_MAX_OVERFLOW,
        "pool_pre_ping": True,
    }),
    echo=settings.DEBUG,
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


AsyncSessionDep = Annotated[AsyncSession, Depends(get_db)]


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
