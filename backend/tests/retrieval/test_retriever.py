"""DocumentRetriever orchestration, with every I/O boundary monkeypatched
(matches the pattern in tests/api/test_chat_endpoints.py) — no real DB or
Gemini call."""

import uuid

import pytest

from app.database import documents
from app.database.models.document_chunk import DocumentChunk
from app.retrieval import embeddings, queries
from app.retrieval.retriever import DocumentRetriever
from app.retrieval.types import RankedChunkHit

pytestmark = pytest.mark.anyio


class _FakeSessionCtx:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


def _fake_session_factory() -> _FakeSessionCtx:
    return _FakeSessionCtx()


def _chunk(chunk_id: uuid.UUID, document_id: uuid.UUID, chunk_index: int, ticker: str = "AAPL") -> DocumentChunk:
    return DocumentChunk(
        id=chunk_id,
        document_id=document_id,
        chunk_index=chunk_index,
        page=None,
        section="Item 7. Management's Discussion",
        chunk_text=f"chunk {chunk_index} text",
        token_count=10,
        chunk_metadata={
            "ticker": ticker,
            "company_name": "Apple Inc.",
            "filing_type": "10-K",
            "filing_date": "2024-11-01",
            "fiscal_year": 2024,
            "accession_number": "0000320193-24-000123",
        },
    )


@pytest.fixture(autouse=True)
def _stub_embed_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embeddings, "embed_query", lambda _query: [0.1, 0.2, 0.3])


async def test_search_fuses_both_legs_and_favors_chunks_ranked_in_both(monkeypatch: pytest.MonkeyPatch) -> None:
    document_id = uuid.uuid4()
    chunk_a, chunk_b = uuid.uuid4(), uuid.uuid4()

    async def fake_semantic_search(_session: object, _embedding: object, _filters: object, _limit: int) -> list:
        return [RankedChunkHit(chunk_id=chunk_a, rank=1, score=0.9), RankedChunkHit(chunk_id=chunk_b, rank=2, score=0.5)]

    async def fake_fulltext_search(_session: object, _query: str, _filters: object, _limit: int) -> list:
        return [RankedChunkHit(chunk_id=chunk_b, rank=1, score=0.8)]

    async def fake_get_chunks_by_ids(_session: object, ids: list[uuid.UUID]) -> dict:
        chunks = {chunk_a: _chunk(chunk_a, document_id, 3), chunk_b: _chunk(chunk_b, document_id, 5)}
        return {cid: chunks[cid] for cid in ids}

    async def fake_get_surrounding_chunks(_session: object, chunk_id: uuid.UUID, _radius: int) -> list:
        return []

    monkeypatch.setattr(queries, "semantic_search", fake_semantic_search)
    monkeypatch.setattr(queries, "fulltext_search", fake_fulltext_search)
    monkeypatch.setattr(documents, "get_chunks_by_ids", fake_get_chunks_by_ids)
    monkeypatch.setattr(documents, "get_surrounding_chunks", fake_get_surrounding_chunks)

    passages = await DocumentRetriever(session_factory=_fake_session_factory).search("Apple revenue mix")

    # chunk_b is ranked in both legs (semantic #2, fulltext #1); chunk_a only in semantic (#1).
    # Fused: chunk_b's two contributions outscore chunk_a's one.
    assert [p.chunk_id for p in passages] == [chunk_b, chunk_a]
    assert passages[0].ticker == "AAPL"
    assert passages[0].filing_type == "10-K"


async def test_search_attaches_neighbor_chunks_excluding_the_hit_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    document_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    neighbor_before, neighbor_after = uuid.uuid4(), uuid.uuid4()

    async def fake_semantic_search(*_args: object, **_kwargs: object) -> list:
        return [RankedChunkHit(chunk_id=chunk_id, rank=1, score=0.9)]

    async def fake_fulltext_search(*_args: object, **_kwargs: object) -> list:
        return []

    async def fake_get_chunks_by_ids(_session: object, ids: list[uuid.UUID]) -> dict:
        return {chunk_id: _chunk(chunk_id, document_id, 5)}

    async def fake_get_surrounding_chunks(_session: object, _chunk_id: uuid.UUID, _radius: int) -> list:
        return [_chunk(neighbor_before, document_id, 4), _chunk(chunk_id, document_id, 5), _chunk(neighbor_after, document_id, 6)]

    monkeypatch.setattr(queries, "semantic_search", fake_semantic_search)
    monkeypatch.setattr(queries, "fulltext_search", fake_fulltext_search)
    monkeypatch.setattr(documents, "get_chunks_by_ids", fake_get_chunks_by_ids)
    monkeypatch.setattr(documents, "get_surrounding_chunks", fake_get_surrounding_chunks)

    passages = await DocumentRetriever(session_factory=_fake_session_factory).search("query")

    assert len(passages) == 1
    neighbor_ids = [n.chunk_id for n in passages[0].neighbors]
    assert neighbor_ids == [neighbor_before, neighbor_after]
    assert chunk_id not in neighbor_ids


async def test_search_skips_a_fused_hit_that_hydration_could_not_find(monkeypatch: pytest.MonkeyPatch) -> None:
    document_id = uuid.uuid4()
    chunk_found, chunk_missing = uuid.uuid4(), uuid.uuid4()

    async def fake_semantic_search(*_args: object, **_kwargs: object) -> list:
        return [
            RankedChunkHit(chunk_id=chunk_missing, rank=1, score=0.9),
            RankedChunkHit(chunk_id=chunk_found, rank=2, score=0.5),
        ]

    async def fake_fulltext_search(*_args: object, **_kwargs: object) -> list:
        return []

    async def fake_get_chunks_by_ids(_session: object, ids: list[uuid.UUID]) -> dict:
        return {chunk_found: _chunk(chunk_found, document_id, 1)}  # chunk_missing not returned

    async def fake_get_surrounding_chunks(*_args: object, **_kwargs: object) -> list:
        return []

    monkeypatch.setattr(queries, "semantic_search", fake_semantic_search)
    monkeypatch.setattr(queries, "fulltext_search", fake_fulltext_search)
    monkeypatch.setattr(documents, "get_chunks_by_ids", fake_get_chunks_by_ids)
    monkeypatch.setattr(documents, "get_surrounding_chunks", fake_get_surrounding_chunks)

    passages = await DocumentRetriever(session_factory=_fake_session_factory).search("query")

    assert [p.chunk_id for p in passages] == [chunk_found]
