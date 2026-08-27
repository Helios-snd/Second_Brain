"""Agent wiring under a fake model — no network. The grounded-answer contract
itself is tested in tests/grounding/ and tests/chat/; here we only check that
the tools feed the TurnRegistry and the output is typed."""

import pytest
from pydantic_ai.models.test import TestModel

from app.assistant import agent as agent_module
from app.assistant.deps import DocumentAgentDeps, TurnRegistry
from app.assistant.outputs import GroundedAnswer
from tests.assistant._factories import make_passage

pytestmark = pytest.mark.anyio

# Real model calls are blocked for unmarked tests by the conftest guard; these
# tests also swap in TestModel via `agent.override`, so they never touch Gemini.


class _FakeRetriever:
    def __init__(self, passages: list) -> None:
        self._passages = passages
        self.calls: list[str] = []

    async def search(self, query: str, filters=None) -> list:
        self.calls.append(query)
        return self._passages


def _deps(retriever) -> DocumentAgentDeps:
    return DocumentAgentDeps(
        user_id="u1",
        thread_id="t1",
        retriever=retriever,
        session_factory=None,  # unused: TestModel only calls search_filings here
        registry=TurnRegistry(),
    )


async def test_search_filings_tool_populates_registry_and_output_is_typed() -> None:
    passage = make_passage()
    retriever = _FakeRetriever([passage])
    deps = _deps(retriever)

    output = GroundedAnswer(
        answer="Services revenue rose [1].",
        citations=[{"citation_index": 1, "chunk_id": str(passage.chunk_id), "excerpt": "rose"}],
    )

    with agent_module.agent.override(
        model=TestModel(call_tools=["search_filings"], custom_output_args=output.model_dump(mode="json")),
        deps=deps,
    ):
        result = await agent_module.agent.run("How did Apple services revenue change?", deps=deps)

    assert retriever.calls  # the agent actually searched
    assert passage.chunk_id in deps.registry
    assert isinstance(result.output, GroundedAnswer)
    assert result.output.citations[0].chunk_id == passage.chunk_id


async def test_agent_can_declare_insufficient_evidence() -> None:
    retriever = _FakeRetriever([])
    deps = _deps(retriever)

    output = GroundedAnswer(answer="No Tesla filings in the corpus.", citations=[], insufficient_evidence=True)

    with agent_module.agent.override(
        model=TestModel(call_tools=["search_filings"], custom_output_args=output.model_dump(mode="json")),
        deps=deps,
    ):
        result = await agent_module.agent.run("What is Tesla's 2023 margin?", deps=deps)

    assert result.output.insufficient_evidence is True
    assert result.output.citations == []
