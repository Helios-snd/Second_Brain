"""Typed shapes for retrieval — shared by queries.py, retriever.py, tests, and
future Phase 6 agent tools (`search_filings`, `read_chunk`, `read_surrounding_chunks`
per docs/architecture.md).

Field names mirror `document_chunks.chunk_metadata` (see
`ingest/load_document_chunks.py::build_chunk_metadata`), not `source_documents`
directly — retrieval reads filing metadata off the denormalized JSONB blob on
each chunk, so it never needs to join `source_documents`.
"""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel


class SearchFilters(BaseModel):
    """Optional scoping for a retrieval query, e.g. "Apple's 2021-2025 10-Ks"."""

    ticker: str | None = None
    fiscal_years: list[int] | None = None
    filing_type: str | None = None  # e.g. "10-K"


class RankedChunkHit(BaseModel):
    """One row from a single retrieval leg (semantic or full-text), in rank order."""

    chunk_id: uuid.UUID
    rank: int
    score: float | None = None  # raw per-leg score; informational only — RRF fuses by rank, not this


class RetrievedPassage(BaseModel):
    """A fused, ranked passage plus its neighbor chunks, ready to ground an answer."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    text: str
    page: int | None
    section: str | None
    fusion_score: float
    ticker: str
    company_name: str | None
    filing_type: str
    filing_date: date
    fiscal_year: int | None
    accession_number: str
    neighbors: list[RetrievedPassage] = []
