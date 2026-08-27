"""The trust contract: an assistant answer only ships if every citation maps to a
passage the agent actually retrieved this turn, and every `[n]` marker in the
prose has a matching citation.

`validate_grounding` is a pure function — no LLM, no I/O — so the contract is
covered by fast unit tests. The caller (`chat/orchestrator.py`) turns a
`GroundingError` into a controlled failure rather than streaming an unsupported
answer.
"""

from __future__ import annotations

import re

from app.assistant.deps import TurnRegistry
from app.assistant.outputs import GroundedAnswer, SourcePassage

_MARKER_RE = re.compile(r"\[(\d+)\]")


class GroundingError(Exception):
    """Raised when an answer violates the grounding contract."""


def _markers_in(text: str) -> set[int]:
    return {int(m) for m in _MARKER_RE.findall(text)}


def validate_grounding(answer: GroundedAnswer, registry: TurnRegistry) -> list[SourcePassage]:
    """Return the cited `SourcePassage`s, or raise `GroundingError`.

    A `insufficient_evidence` answer is expected to carry no citations and is
    returned as an empty list — the caller streams the model's explanation.
    """
    if answer.insufficient_evidence:
        if answer.citations:
            raise GroundingError("insufficient_evidence answer must not carry citations")
        return []

    markers = _markers_in(answer.answer)
    cited_indexes = {c.citation_index for c in answer.citations}

    if not markers:
        raise GroundingError("answer makes claims with no [n] citation markers")
    # Every marker must resolve to a citation. An extra citation the model listed
    # but never anchored with a marker is unused, not a violation — drop it below.
    unbacked = markers - cited_indexes
    if unbacked:
        raise GroundingError(f"citation markers {sorted(unbacked)} have no matching citation")

    passages: list[SourcePassage] = []
    for citation in sorted(answer.citations, key=lambda c: c.citation_index):
        if citation.citation_index not in markers:
            continue  # listed but never cited in the prose — skip
        retrieved = registry.get(citation.chunk_id)
        if retrieved is None:
            raise GroundingError(f"citation [{citation.citation_index}] cites unretrieved chunk {citation.chunk_id}")
        passages.append(
            SourcePassage(
                citation_index=citation.citation_index,
                chunk_id=citation.chunk_id,
                excerpt=citation.excerpt,
                text=retrieved.text,
                ticker=retrieved.ticker,
                company_name=retrieved.company_name,
                filing_type=retrieved.filing_type,
                filing_date=retrieved.filing_date,
                fiscal_year=retrieved.fiscal_year,
                section=retrieved.section,
            )
        )
    return passages
