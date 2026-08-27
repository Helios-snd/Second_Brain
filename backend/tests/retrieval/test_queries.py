"""Unit tests for the SQL boundary — a fake AsyncSession captures the bound
params instead of hitting a real database, so these run in the fast suite.
First test module in the repo exercising the SQLAlchemy session boundary
(everything else persists through the Supabase client)."""

import uuid
from dataclasses import dataclass
from typing import Any

import pytest

from app.retrieval import queries
from app.retrieval.types import SearchFilters

pytestmark = pytest.mark.anyio


@dataclass
class _FakeRow:
    id: uuid.UUID
    score: float


class _FakeResult:
    def __init__(self, rows: list[_FakeRow]) -> None:
        self._rows = rows

    def all(self) -> list[_FakeRow]:
        return self._rows


class _FakeSession:
    def __init__(self, rows: list[_FakeRow]) -> None:
        self._rows = rows
        self.last_params: dict[str, Any] | None = None

    async def execute(self, _statement: object, params: dict[str, Any]) -> _FakeResult:
        self.last_params = params
        return _FakeResult(self._rows)


async def test_semantic_search_returns_hits_in_row_order_with_1_based_rank() -> None:
    chunk_1, chunk_2 = uuid.uuid4(), uuid.uuid4()
    session = _FakeSession([_FakeRow(chunk_1, 0.9), _FakeRow(chunk_2, 0.5)])

    hits = await queries.semantic_search(session, [0.1, 0.2], SearchFilters(), limit=10)

    assert [(h.chunk_id, h.rank, h.score) for h in hits] == [(chunk_1, 1, 0.9), (chunk_2, 2, 0.5)]


async def test_semantic_search_passes_query_vector_and_limit() -> None:
    session = _FakeSession([])
    embedding = [0.1, 0.2, 0.3]

    await queries.semantic_search(session, embedding, SearchFilters(), limit=7)

    assert session.last_params["query_vec"] == embedding
    assert session.last_params["limit"] == 7


async def test_semantic_search_leaves_absent_filters_as_none() -> None:
    session = _FakeSession([])

    await queries.semantic_search(session, [0.0], SearchFilters(), limit=5)

    assert session.last_params["ticker"] is None
    assert session.last_params["fiscal_years"] is None
    assert session.last_params["filing_type"] is None


async def test_semantic_search_converts_fiscal_years_to_strings_for_the_text_array_cast() -> None:
    session = _FakeSession([])

    await queries.semantic_search(session, [0.0], SearchFilters(fiscal_years=[2023, 2024]), limit=5)

    assert session.last_params["fiscal_years"] == ["2023", "2024"]


async def test_semantic_search_passes_ticker_and_filing_type_through() -> None:
    session = _FakeSession([])

    await queries.semantic_search(session, [0.0], SearchFilters(ticker="AAPL", filing_type="10-K"), limit=5)

    assert session.last_params["ticker"] == "AAPL"
    assert session.last_params["filing_type"] == "10-K"


async def test_fulltext_search_passes_query_text_and_configured_fts_config() -> None:
    session = _FakeSession([])

    await queries.fulltext_search(session, "Apple revenue mix", SearchFilters(), limit=10)

    assert session.last_params["query_text"] == "Apple revenue mix"
    assert session.last_params["fts_config"] == "english"  # settings.retrieval_fts_config default


async def test_fulltext_search_returns_hits_in_row_order() -> None:
    chunk_1, chunk_2 = uuid.uuid4(), uuid.uuid4()
    session = _FakeSession([_FakeRow(chunk_1, 0.8), _FakeRow(chunk_2, 0.3)])

    hits = await queries.fulltext_search(session, "AWS margin", SearchFilters(), limit=10)

    assert [h.chunk_id for h in hits] == [chunk_1, chunk_2]
