import json

import pytest

from app.chat import streaming

pytestmark = pytest.mark.anyio


async def test_iter_stub_reply_chunks_sequence_and_text() -> None:
    chunks = [chunk async for chunk in streaming.iter_stub_reply_chunks("msg-1")]

    types = [chunk.type for chunk in chunks]
    assert types[0] == "start"
    assert types[1] == "text-start"
    assert types[-2] == "text-end"
    assert types[-1] == "finish"
    assert all(t == "text-delta" for t in types[2:-2])

    deltas = "".join(chunk.delta for chunk in chunks if chunk.type == "text-delta")
    assert deltas == streaming.STUB_REPLY_TEXT


async def test_encode_chunk_sse_framing() -> None:
    [start_chunk, *_rest] = [chunk async for chunk in streaming.iter_stub_reply_chunks("msg-1")]

    encoded = streaming.encode_chunk(start_chunk)

    assert encoded.startswith("data: ")
    assert encoded.endswith("\n\n")
    payload = json.loads(encoded.removeprefix("data: ").removesuffix("\n\n"))
    assert payload == {"type": "start", "messageId": "msg-1"}
