import uuid

import pytest

from app.assistant.deps import TurnRegistry
from app.assistant.outputs import Citation, GroundedAnswer
from app.grounding.validator import GroundingError, validate_grounding
from tests.assistant._factories import make_passage


def _registry(*passages) -> TurnRegistry:
    registry = TurnRegistry()
    registry.register(passages)
    return registry


def test_valid_answer_returns_source_passages() -> None:
    passage = make_passage(text="Services revenue was $96.2 billion.")
    answer = GroundedAnswer(
        answer="Services revenue was $96.2 billion [1].",
        citations=[Citation(citation_index=1, chunk_id=passage.chunk_id, excerpt="$96.2 billion")],
    )

    [source] = validate_grounding(answer, _registry(passage))

    assert source.citation_index == 1
    assert source.chunk_id == passage.chunk_id
    assert source.ticker == "AAPL"
    assert source.text == "Services revenue was $96.2 billion."


def test_citation_to_unretrieved_chunk_fails_closed() -> None:
    passage = make_passage()
    answer = GroundedAnswer(
        answer="Something happened [1].",
        citations=[Citation(citation_index=1, chunk_id=uuid.uuid4(), excerpt="x")],
    )

    with pytest.raises(GroundingError, match="unretrieved chunk"):
        validate_grounding(answer, _registry(passage))


def test_factual_answer_with_no_markers_fails_closed() -> None:
    answer = GroundedAnswer(answer="Revenue grew sharply in 2024.", citations=[])

    with pytest.raises(GroundingError, match="no .n. citation markers"):
        validate_grounding(answer, TurnRegistry())


def test_marker_without_backing_citation_fails_closed() -> None:
    passage = make_passage()
    answer = GroundedAnswer(
        answer="Claim one [1]. Claim two [2].",
        citations=[Citation(citation_index=1, chunk_id=passage.chunk_id, excerpt="x")],
    )

    with pytest.raises(GroundingError, match="have no matching citation"):
        validate_grounding(answer, _registry(passage))


def test_extra_unanchored_citation_is_dropped_not_fatal() -> None:
    p1, p2 = make_passage(text="anchored"), make_passage(text="never referenced")
    answer = GroundedAnswer(
        answer="Only claim one is marked [1].",
        citations=[
            Citation(citation_index=1, chunk_id=p1.chunk_id, excerpt="anchored"),
            Citation(citation_index=2, chunk_id=p2.chunk_id, excerpt="extra"),
        ],
    )

    sources = validate_grounding(answer, _registry(p1, p2))

    assert [s.citation_index for s in sources] == [1]


def test_insufficient_evidence_bypasses_citation_checks() -> None:
    answer = GroundedAnswer(
        answer="The corpus has no Tesla filings, so this cannot be answered.",
        citations=[],
        insufficient_evidence=True,
    )

    assert validate_grounding(answer, TurnRegistry()) == []


def test_insufficient_evidence_with_citations_fails_closed() -> None:
    passage = make_passage()
    answer = GroundedAnswer(
        answer="Not enough evidence [1].",
        citations=[Citation(citation_index=1, chunk_id=passage.chunk_id, excerpt="x")],
        insufficient_evidence=True,
    )

    with pytest.raises(GroundingError):
        validate_grounding(answer, _registry(passage))


def test_neighbors_are_registered_and_citable() -> None:
    neighbor = make_passage(text="neighbor context")
    hit = make_passage(neighbors=[neighbor])
    answer = GroundedAnswer(
        answer="Per surrounding context [1].",
        citations=[Citation(citation_index=1, chunk_id=neighbor.chunk_id, excerpt="neighbor")],
    )

    [source] = validate_grounding(answer, _registry(hit))

    assert source.chunk_id == neighbor.chunk_id
