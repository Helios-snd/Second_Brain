"""Stubbed assistant reply, encoded as AI SDK v5 UI Message Stream chunks.

Pure protocol logic — no Supabase calls, no `HTTPException`. This is the seam
Phase 6 replaces wholesale with real `pydantic_ai.Agent` streaming; everything
here only exists because there's no agent yet.
"""

import asyncio
from collections.abc import AsyncIterator

from pydantic_ai.ui.vercel_ai.response_types import (
    BaseChunk,
    FinishChunk,
    StartChunk,
    TextDeltaChunk,
    TextEndChunk,
    TextStartChunk,
)

# Matches VERCEL_AI_DSP_HEADERS in pydantic_ai.ui.vercel_ai._event_stream — the
# AI SDK client uses this header to select its stream parser.
STREAM_HEADERS = {"x-vercel-ai-ui-message-stream": "v1"}

STUB_REPLY_TEXT = (
    "Thanks for the question. Retrieval and grounded answers aren't wired up yet "
    "— this is a placeholder reply so the chat shell can be verified end to end."
)

_DELTA_DELAY_SECONDS = 0.03


def encode_chunk(chunk: BaseChunk, sdk_version: int = 5) -> str:
    return f"data: {chunk.encode(sdk_version)}\n\n"


async def iter_stub_reply_chunks(message_id: str) -> AsyncIterator[BaseChunk]:
    """Pure chunk sequence for a canned assistant reply. Callers accumulate the
    full text themselves for persistence (see app/api/chat.py)."""
    yield StartChunk(message_id=message_id)
    yield TextStartChunk(id=message_id)
    words = STUB_REPLY_TEXT.split(" ")
    for index, word in enumerate(words):
        delta = word if index == 0 else f" {word}"
        yield TextDeltaChunk(id=message_id, delta=delta)
        await asyncio.sleep(_DELTA_DELAY_SECONDS)
    yield TextEndChunk(id=message_id)
    yield FinishChunk(finish_reason="stop")
