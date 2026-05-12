"""Async SQLAlchemy engine and session factory.

The engine is lazy — created on first call, disposed by :func:`close_engine`
in the FastAPI lifespan. Wrapping the singletons in a ClassVar container
keeps mypy strict and ruff happy without ``global`` statements.
"""

from collections.abc import AsyncIterator
from typing import ClassVar

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from promptwall.settings import get_settings


class _DBState:
    engine: ClassVar[AsyncEngine | None] = None
    factory: ClassVar[async_sessionmaker[AsyncSession] | None] = None


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine (lazy)."""
    if _DBState.engine is None:
        _DBState.engine = create_async_engine(
            get_settings().database_url,
            pool_pre_ping=True,
        )
    return _DBState.engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the session factory bound to the engine."""
    if _DBState.factory is None:
        _DBState.factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _DBState.factory


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency — yields an AsyncSession bound to the engine."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def close_engine() -> None:
    """Dispose the engine. Idempotent."""
    if _DBState.engine is not None:
        await _DBState.engine.dispose()
        _DBState.engine = None
        _DBState.factory = None
