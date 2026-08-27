"""Typed query helpers for chat threads and messages.

Persistence goes through the Supabase client (PostgREST), not a SQLAlchemy
session, so RLS ("users see only their own chats") applies automatically.
`app/database/session.py`'s async engine exists for retrieval, where pgvector
distance ordering and ranked full-text search need real SQL PostgREST can't
express — but chat data is per-user-scoped, so it stays on the RLS-enforcing
client. Callers pick the RLS-scoped client for normal reads/writes, and reach
for `thread_exists_privileged` only to disambiguate 403 from 404 (see
app/api/chat.py).
"""

from datetime import UTC, datetime
from typing import Any

from supabase import AsyncClient

from app.database.supabase import get_service_client


async def list_threads(client: AsyncClient) -> list[dict[str, Any]]:
    """Threads for the caller. RLS (`chat_threads_select_own`) scopes this to
    `auth.uid()` — no explicit user_id filter needed."""
    result = await client.table("chat_threads").select("*").order("updated_at", desc=True).execute()
    return result.data


async def create_thread(client: AsyncClient, *, user_id: str, title: str | None) -> dict[str, Any]:
    result = await client.table("chat_threads").insert({"user_id": user_id, "title": title}).execute()
    return result.data[0]


async def fetch_thread_as_user(client: AsyncClient, thread_id: str) -> dict[str, Any] | None:
    """`None` if the thread doesn't exist OR belongs to another user — RLS makes
    these indistinguishable here by design. Disambiguate with `thread_exists_privileged`."""
    result = await client.table("chat_threads").select("*").eq("id", thread_id).maybe_single().execute()
    return result.data if result is not None else None


async def thread_exists_privileged(thread_id: str) -> bool:
    """Service-role existence check, bypassing RLS. Used ONLY to distinguish 404
    (no row) from 403 (row exists, owned by someone else) after
    `fetch_thread_as_user` returns None — never to read or return thread data."""
    result = (
        await get_service_client().table("chat_threads").select("id").eq("id", thread_id).maybe_single().execute()
    )
    return result is not None


async def list_messages(client: AsyncClient, thread_id: str) -> list[dict[str, Any]]:
    result = (
        await client.table("chat_messages").select("*").eq("thread_id", thread_id).order("created_at").execute()
    )
    return result.data


async def insert_message(
    client: AsyncClient,
    *,
    message_id: str,
    thread_id: str,
    role: str,
    content: str,
    parts: list[dict[str, Any]],
) -> dict[str, Any]:
    """`message_id` is caller-supplied (not left to the DB default) so the id
    streamed to the client matches the persisted row's id exactly."""
    result = (
        await client.table("chat_messages")
        .insert({"id": message_id, "thread_id": thread_id, "role": role, "content": content, "parts": parts})
        .execute()
    )
    return result.data[0]


async def insert_citations(message_id: str, citations: list[dict[str, Any]]) -> None:
    """Normalized `message_citations` rows for an assistant message.

    `message_citations` has an RLS SELECT policy but no INSERT policy (see the
    core-tables migration), so this writes with the service-role client — same
    precedent as ingestion. `citations` items are `{"chunk_id", "excerpt"}`.
    """
    if not citations:
        return
    rows = [{"message_id": message_id, **citation} for citation in citations]
    await get_service_client().table("message_citations").insert(rows).execute()


async def touch_thread(client: AsyncClient, thread_id: str) -> None:
    """`chat_threads.updated_at` has SQLAlchemy-side `onupdate=func.now()`, which
    only fires for ORM-mediated UPDATEs — it does nothing for PostgREST writes.
    Bump it explicitly so thread lists can order by last activity."""
    await client.table("chat_threads").update({"updated_at": datetime.now(UTC).isoformat()}).eq(
        "id", thread_id
    ).execute()
