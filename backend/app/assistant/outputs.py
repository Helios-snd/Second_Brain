"""Typed agent output for a grounded answer.

`GroundedAnswer` is the agent's `output_type` — the model must return this shape.
`SourcePassage` is *not* model-produced: `grounding/validator.py` builds it from
the turn's `TurnRegistry` for the chunks the model actually cited, so citation
metadata (ticker, filing, date) can't be hallucinated.
"""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """One `[n]` marker in the answer, tied to a retrieved chunk."""

    citation_index: int = Field(description="The [n] marker this citation backs, e.g. 1 for [1].")
    chunk_id: uuid.UUID = Field(description="A chunk_id returned by a tool this turn.")
    excerpt: str = Field(description="A short verbatim quote from that chunk supporting the claim.")


class GroundedAnswer(BaseModel):
    """The agent's answer for one chat turn."""

    answer: str = Field(description="The answer, with [n] markers on every factual claim.")
    citations: list[Citation] = Field(default_factory=list)
    insufficient_evidence: bool = Field(
        default=False,
        description="True when the corpus does not support an answer; leave citations empty.",
    )


class SourcePassage(BaseModel):
    """A cited passage with citation-display metadata, assembled by the validator."""

    citation_index: int
    chunk_id: uuid.UUID
    excerpt: str
    text: str
    ticker: str
    company_name: str | None
    filing_type: str
    filing_date: date
    fiscal_year: int | None
    section: str | None
