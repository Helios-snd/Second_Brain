"""Real DB + real Gemini, run against the ingested corpus. This doubles as
Phase 5's "Verify: test queries from client-brief return relevant chunks"
checklist item — questions are taken directly from docs/client-brief.md's
example analyst questions.

Phase 4 ingestion is still in progress (docs/todos.md) — as of writing, only
AAPL, MSFT, and NVDA have embedded chunks; AMZN and GOOGL don't yet. Tests
here stick to companies that are actually ingested so this file's pass/fail
reflects retrieval correctness, not ingestion completeness; re-add
AMZN/GOOGL-specific cases once their filings are chunked and embedded.

Run with: uv run pytest -m integration tests/retrieval/
"""

import pytest

from app.retrieval.retriever import DocumentRetriever
from app.retrieval.types import SearchFilters

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


async def test_apple_revenue_mix_question_returns_apple_passages() -> None:
    passages = await DocumentRetriever().search(
        "How has Apple's revenue mix shifted across its 2021-2025 10-Ks?",
        filters=SearchFilters(ticker="AAPL"),
    )

    assert passages
    assert all(p.ticker == "AAPL" for p in passages)


async def test_nvidia_data_center_question_surfaces_nvidia_passages() -> None:
    passages = await DocumentRetriever().search(
        "What is driving demand for NVIDIA's Data Center segment?",
        filters=SearchFilters(ticker="NVDA"),
    )

    assert passages
    assert all(p.ticker == "NVDA" for p in passages)


async def test_microsoft_azure_question_returns_relevant_passages_without_filters() -> None:
    passages = await DocumentRetriever().search(
        "What changed in how Microsoft describes Azure and AI infrastructure capacity constraints?"
    )

    assert passages
    assert any(p.ticker == "MSFT" for p in passages)


async def test_cross_company_risk_factor_question_spans_multiple_filers() -> None:
    passages = await DocumentRetriever().search(
        "How does risk-factor language about AI and export controls compare across companies?"
    )

    assert passages
    tickers = {p.ticker for p in passages}
    assert len(tickers) > 1  # a cross-company question should not collapse onto a single filer


async def test_neighbor_chunks_are_attached_and_from_the_same_document() -> None:
    passages = await DocumentRetriever().search(
        "What are Apple's supplier concentration risks?", filters=SearchFilters(ticker="AAPL")
    )

    assert passages
    top = passages[0]
    assert all(n.document_id == top.document_id for n in top.neighbors)
