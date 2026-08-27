"""Orchestrator turn lifecycle with retriever + agent faked — no DB, no LLM."""

from typing import Any

import pytest

from app.assistant.outputs import Citation, GroundedAnswer
from app.chat import orchestrator
from app.grounding.validator import GroundingError
from tests.assistant._factories import make_passage

pytestmark = pytest.mark.anyio


class _FakeRetriever:
    def __init__(self, passages: list) -> None:
        self._passages = passages
        self.queries: list[str] = []

    async def search(self, query: str, filters: Any = None) -> list:
        self.queries.append(query)
        return self._passages


class _FakeResult:
    def __init__(self, output: GroundedAnswer) -> None:
        self.output = output


class _FakeAgent:
    def __init__(self, output: GroundedAnswer, seen: dict) -> None:
        self._output = output
        self._seen = seen

    async def run(self, prompt: str, **kwargs: Any) -> _FakeResult:
        self._seen["prompt"] = prompt
        self._seen["deps"] = kwargs["deps"]
        self._seen["usage_limits"] = kwargs.get("usage_limits")
        return _FakeResult(self._output)


def _install(monkeypatch: pytest.MonkeyPatch, retriever: _FakeRetriever, output: GroundedAnswer) -> dict:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(orchestrator, "DocumentRetriever", lambda: retriever)
    monkeypatch.setattr(orchestrator, "get_session_factory", lambda: None)
    monkeypatch.setattr(orchestrator, "agent", _FakeAgent(output, seen))
    return seen


async def test_grounded_turn_returns_validated_passages(monkeypatch: pytest.MonkeyPatch) -> None:
    passage = make_passage(text="Services revenue was $96.2 billion.")
    retriever = _FakeRetriever([passage])
    output = GroundedAnswer(
        answer="Services revenue was $96.2 billion [1].",
        citations=[Citation(citation_index=1, chunk_id=passage.chunk_id, excerpt="$96.2 billion")],
    )
    seen = _install(monkeypatch, retriever, output)

    result = await orchestrator.run_turn(
        user_id="u1", thread_id="t1", history=[], question="How did Apple services revenue change?"
    )

    assert result.kind == "grounded"
    assert [p.chunk_id for p in result.passages] == [passage.chunk_id]
    assert result.answer_text == output.answer
    assert retriever.queries == ["How did Apple services revenue change?"]  # seed search ran
    assert seen["usage_limits"] is not None  # request_limit passed


async def test_insufficient_evidence_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    retriever = _FakeRetriever([])
    output = GroundedAnswer(
        answer="The corpus has no Tesla filings.", citations=[], insufficient_evidence=True
    )
    _install(monkeypatch, retriever, output)

    result = await orchestrator.run_turn(
        user_id="u1", thread_id="t1", history=[], question="Tesla 2023 margin?"
    )

    assert result.kind == "insufficient"
    assert result.passages == []
    assert result.citations == []


async def test_grounding_violation_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    import uuid

    retriever = _FakeRetriever([make_passage()])
    output = GroundedAnswer(
        answer="Fabricated claim [1].",
        citations=[Citation(citation_index=1, chunk_id=uuid.uuid4(), excerpt="nope")],
    )
    _install(monkeypatch, retriever, output)

    with pytest.raises(GroundingError):
        await orchestrator.run_turn(user_id="u1", thread_id="t1", history=[], question="q")
