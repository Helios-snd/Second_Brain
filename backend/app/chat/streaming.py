"""Turn output, encoded as AI SDK v5 UI Message Stream chunks.

Pure protocol logic — no Supabase, no `HTTPException`. The validated answer text
is already complete by the time we get here (grounding must pass *before* any
text streams), so `iter_answer_chunks` replays it as word-level deltas; true
token streaming from the model is a later optimization.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from pydantic_ai.ui.vercel_ai.response_types import (
    BaseChunk,
    DataChunk,
    ErrorChunk,
    FinishChunk,
    StartChunk,
    TextDeltaChunk,
    TextEndChunk,
    TextStartChunk,
)

from app.chat.messages import CITATION_PART_TYPE

# Matches VERCEL_AI_DSP_HEADERS in pydantic_ai.ui.vercel_ai._event_stream — the
# AI SDK client uses this header to select its stream parser.
STREAM_HEADERS = {"x-vercel-ai-ui-message-stream": "v1"}

_DELTA_DELAY_SECONDS = 0.02

_VIOLATION_TEXT = "Could not produce an answer grounded in the corpus for this question."


def encode_chunk(chunk: BaseChunk, sdk_version: int = 5) -> str:
    return f"data: {chunk.encode(sdk_version)}\n\n"


async def iter_answer_chunks(
    message_id: str, answer_text: str, citation_data: list[dict[str, Any]]
) -> AsyncIterator[BaseChunk]:
    """A grounded (or honest 'not enough evidence') answer: word deltas, then one
    citation data part if there are citations."""
    yield StartChunk(message_id=message_id)
    yield TextStartChunk(id=message_id)
    for index, word in enumerate(answer_text.split(" ")):
        yield TextDeltaChunk(id=message_id, delta=word if index == 0 else f" {word}")
        await asyncio.sleep(_DELTA_DELAY_SECONDS)
    yield TextEndChunk(id=message_id)
    if citation_data:
        yield DataChunk(type=CITATION_PART_TYPE, data=citation_data)
    yield FinishChunk(finish_reason="stop")


async def iter_violation_chunks(message_id: str) -> AsyncIterator[BaseChunk]:
    """A grounding violation: an error event, nothing persisted."""
    yield StartChunk(message_id=message_id)
    yield ErrorChunk(error_text=_VIOLATION_TEXT)
    yield FinishChunk(finish_reason="error")
