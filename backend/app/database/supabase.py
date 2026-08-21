"""Supabase client factories.

Two flavors, matching the RLS policies from the core tables migration:
- Service-role client bypasses RLS entirely — backend-only (ingestion, admin).
- User-scoped client carries the caller's JWT, so Postgres sees the real
  `auth.uid()` and enforces "users see only their own chats" policies.
"""

from functools import cache

from supabase import AsyncClient, AsyncClientOptions

from app.config import settings


@cache
def get_service_client() -> AsyncClient:
    """Singleton service-role client. Bypasses RLS — never expose to end users."""
    return AsyncClient(settings.supabase_url, settings.supabase_service_role_key)


def get_user_client(access_token: str) -> AsyncClient:
    """Per-request client scoped to the caller's JWT, so RLS applies as that user.

    Built directly rather than via `create_async_client`/`AsyncClient.create`,
    which try to look up a persisted session — irrelevant here since a
    stateless backend only ever has the caller's bearer token.
    """
    options = AsyncClientOptions(headers={"Authorization": f"Bearer {access_token}"})
    return AsyncClient(settings.supabase_url, settings.supabase_anon_key, options)
