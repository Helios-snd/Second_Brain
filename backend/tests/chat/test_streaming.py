import json

import pytest

from app.chat import streaming
from app.chat.messages import CITATION_PART_TYPE

pytestmark = pytest.mark.anyio

_CITATION = {"citation_index": 1, "chunk_id": "c1", "excerpt": "…"}


async def test_iter_answer_chunks_sequence_and_text() -> None:
    chunks = [c async for c in streaming.iter_answer_chunks("msg-1", "hello grounded world", [_CITATION])]

    types = [c.type for c in chunks]
    assert types[0] == "start"
    assert types[1] == "text-start"
    assert types[-3] == "text-end"
    assert types[-2] == CITATION_PART_TYPE
    assert types[-1] == "finish"

    deltas = "".join(c.delta for c in chunks if c.type == "text-delta")
    assert deltas == "hello grounded world"

    data_chunk = next(c for c in chunks if c.type == CITATION_PART_TYPE)
    assert data_chunk.data == [_CITATION]


async def test_iter_answer_chunks_omits_data_part_when_no_citations() -> None:
    chunks = [c async for c in streaming.iter_answer_chunks("msg-1", "not enough evidence", [])]

    assert [c.type for c in chunks][-2:] == ["text-end", "finish"]
    assert not any(c.type == CITATION_PART_TYPE for c in chunks)


async def test_iter_violation_chunks_emits_error() -> None:
    chunks = [c async for c in streaming.iter_violation_chunks("msg-1")]

    assert [c.type for c in chunks] == ["start", "error", "finish"]
    assert chunks[-1].finish_reason == "error"


async def test_encode_chunk_sse_framing() -> None:
    [start_chunk, *_rest] = [c async for c in streaming.iter_violation_chunks("msg-1")]

    encoded = streaming.encode_chunk(start_chunk)

    assert encoded.startswith("data: ")
    assert encoded.endswith("\n\n")
    payload = json.loads(encoded.removeprefix("data: ").removesuffix("\n\n"))
    assert payload == {"type": "start", "messageId": "msg-1"}
