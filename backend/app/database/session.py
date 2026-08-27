"""Async SQLAlchemy engine + session factory for direct SQL against Postgres.

Everything else in `app/database/` goes through the Supabase client
(PostgREST) — see `chats.py`. Retrieval is the exception: pgvector distance
ordering (`embedding <=> :query_vec`) and ranked full-text search
(`ts_rank_cd`) both need query-time values inside `ORDER BY`, which
PostgREST's filter API can't express. `psycopg[binary]` is already a pinned
dependency and its SQLAlchemy dialect supports async natively under the same
`postgresql+psycopg://` URL, so this needs no new dependency.
"""

import sys
from functools import cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

if sys.platform == "win32":
    # psycopg3's async mode cannot run on Windows' default ProactorEventLoop
    # (raises psycopg.InterfaceError on connect) — only affects local dev,
    # since Railway hosting is Linux. Must run before any event loop starts,
    # so this sets the policy at import time rather than inside get_engine().
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _async_database_url() -> str:
    # settings.database_url is the plain postgresql:// URL from Supabase (the
    # direct/session connection — see config.py); force the psycopg (v3)
    # driver, same as alembic/env.py's _sync_database_url.
    url = settings.database_url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


@cache
def get_engine() -> AsyncEngine:
    return create_async_engine(_async_database_url(), pool_pre_ping=True)


@cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)
