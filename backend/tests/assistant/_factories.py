"""Shared builders for retrieval passages in assistant / grounding / chat tests."""

from __future__ import annotations

import uuid
from datetime import date

from app.retrieval.types import RetrievedPassage


def make_passage(
    *,
    chunk_id: uuid.UUID | None = None,
    text: str = "Services revenue grew to $96.2 billion.",
    ticker: str = "AAPL",
    fiscal_year: int | None = 2024,
    section: str | None = "Item 7. Management's Discussion",
    neighbors: list[RetrievedPassage] | None = None,
) -> RetrievedPassage:
    return RetrievedPassage(
        chunk_id=chunk_id or uuid.uuid4(),
        document_id=uuid.uuid4(),
        chunk_index=3,
        text=text,
        page=None,
        section=section,
        fusion_score=0.5,
        ticker=ticker,
        company_name="Apple Inc.",
        filing_type="10-K",
        filing_date=date(2024, 11, 1),
        fiscal_year=fiscal_year,
        accession_number="0000320193-24-000123",
        neighbors=neighbors or [],
    )
