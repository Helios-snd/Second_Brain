"""Chat thread CRUD and the stubbed streaming reply.

`POST /chat/stream` speaks the AI SDK v5 UI Message Stream protocol via
`pydantic_ai.ui.vercel_ai`'s request/response types, reused directly rather
than hand-rolled — see docs/architecture.md's streaming contract. There's no
real agent yet (Phase 6), so the reply is a fixed canned string; only the
wire protocol is real.
"""

import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from postgrest.exceptions import APIError
from pydantic import BaseModel, TypeAdapter, ValidationError
from pydantic_ai.ui.vercel_ai.request_types import RequestData, TextUIPart, UIMessage
from pydantic_ai.ui.vercel_ai.response_types import DoneChunk, ErrorChunk
from starlette.responses import StreamingResponse
from supabase import AsyncClient
from supabase_auth.types import User

from app.auth.dependencies import get_current_user, get_db_client
from app.chat import streaming
from app.database import chats

router = APIRouter(prefix="/chat", tags=["chat"])

_request_data_ta: TypeAdapter[RequestData] = TypeAdapter(RequestData)


class ThreadSummary(BaseModel):
    id: uuid.UUID
    title: str | None
    created_at: str
    updated_at: str


class CreateThreadRequest(BaseModel):
    title: str | None = None


@router.get("/threads")
async def list_threads(
    user: User = Depends(get_current_user),
    client: AsyncClient = Depends(get_db_client),
) -> list[ThreadSummary]:
    rows = await chats.list_threads(client)
    return [ThreadSummary(**row) for row in rows]


@router.post("/threads")
async def create_thread(
    body: CreateThreadRequest,
    user: User = Depends(get_current_user),
    client: AsyncClient = Depends(get_db_client),
) -> ThreadSummary:
    row = await chats.create_thread(client, user_id=user.id, title=body.title)
    return ThreadSummary(**row)


@router.get("/threads/{thread_id}/messages")
async def get_thread_messages(
    thread_id: uuid.UUID,
    user: User = Depends(get_current_user),
    client: AsyncClient = Depends(get_db_client),
) -> list[UIMessage]:
    await _require_owned_thread(thread_id, client)
    rows = await chats.list_messages(client, str(thread_id))
    return [_row_to_ui_message(row) for row in rows]


@router.post("/stream")
async def stream_chat(
    request: Request,
    user: User = Depends(get_current_user),
    client: AsyncClient = Depends(get_db_client),
) -> StreamingResponse:
    body = _parse_request_body(await request.body())

    try:
        thread_id = uuid.UUID(body.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Thread not found") from exc

    await _require_owned_thread(thread_id, client)

    last_message = body.messages[-1]
    user_text = "".join(part.text for part in last_message.parts if isinstance(part, TextUIPart))

    # `last_message.id` is client-generated (AI SDK's default `generateId()`,
    # not a UUID) — `chat_messages.id` is a Postgres UUID column, so a
    # server-generated id is used here instead of the wire id.
    await chats.insert_message(
        client,
        message_id=str(uuid.uuid4()),
        thread_id=str(thread_id),
        role="user",
        content=user_text,
        parts=[{"type": "text", "text": user_text, "state": "done"}],
    )

    return StreamingResponse(
        _event_source(client, str(thread_id)),
        media_type="text/event-stream",
        headers=streaming.STREAM_HEADERS,
    )


def _parse_request_body(raw: bytes) -> RequestData:
    try:
        return _request_data_ta.validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.errors()) from exc


async def _require_owned_thread(thread_id: uuid.UUID, client: AsyncClient) -> dict[str, Any]:
    """403 vs 404: RLS makes "doesn't exist" and "exists but isn't yours" both
    read as zero rows to a user-scoped client, so a clean status code needs an
    explicit disambiguation step. The common case (owner accessing their own
    thread) never touches the service-role client — only the error path does,
    and even then it reads nothing but `id`."""
    thread = await chats.fetch_thread_as_user(client, str(thread_id))
    if thread is not None:
        return thread
    if await chats.thread_exists_privileged(str(thread_id)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this thread")
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Thread not found")


def _row_to_ui_message(row: dict[str, Any]) -> UIMessage:
    parts = row["parts"] or [{"type": "text", "text": row["content"], "state": "done"}]
    return UIMessage(id=str(row["id"]), role=row["role"], parts=parts)


async def _event_source(client: AsyncClient, thread_id: str) -> AsyncIterator[str]:
    assistant_id = str(uuid.uuid4())
    full_text = ""
    async for chunk in streaming.iter_stub_reply_chunks(assistant_id):
        if hasattr(chunk, "delta"):
            full_text += chunk.delta
        yield streaming.encode_chunk(chunk)

    try:
        await chats.insert_message(
            client,
            message_id=assistant_id,
            thread_id=thread_id,
            role="assistant",
            content=full_text,
            parts=[{"type": "text", "text": full_text, "state": "done"}],
        )
        await chats.touch_thread(client, thread_id)
    except APIError:
        # The HTTP status (200, text/event-stream) is already committed by this
        # point in the stream — a mid-stream failure can only surface as an
        # in-band error event, not a 502 status. Pre-stream failures (ownership
        # check, user-message insert above) still map to clean HTTP status codes.
        yield streaming.encode_chunk(ErrorChunk(error_text="Failed to save assistant reply"))

    yield streaming.encode_chunk(DoneChunk())
