"""One chat turn, end to end: seed retrieval → agent run → grounding check.

The orchestrator owns the turn lifecycle but not its pieces — retrieval lives in
`app/retrieval/`, the LLM boundary in `app/assistant/agent.py`, the trust
contract in `app/grounding/validator.py`. It returns a `TurnResult` the API
layer streams and persists; a grounding *violation* is raised, not returned, so
the API can emit a controlled error instead of an unsupported answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic_ai import UsageLimits
from pydantic_ai.messages import ModelMessage

from app.assistant.agent import agent
from app.assistant.deps import DocumentAgentDeps, TurnRegistry
from app.assistant.outputs import Citation, SourcePassage
from app.config import settings
from app.database.session import get_session_factory
from app.grounding.validator import validate_grounding
from app.retrieval.retriever import DocumentRetriever


@dataclass
class TurnResult:
    answer_text: str
    passages: list[SourcePassage]
    citations: list[Citation]
    kind: Literal["grounded", "insufficient"]


async def run_turn(
    *, user_id: str, thread_id: str, history: list[ModelMessage], question: str
) -> TurnResult:
    retriever = DocumentRetriever()
    registry = TurnRegistry()
    registry.register(await retriever.search(question))

    deps = DocumentAgentDeps(
        user_id=user_id,
        thread_id=thread_id,
        retriever=retriever,
        session_factory=get_session_factory(),
        registry=registry,
    )

    result = await agent.run(
        question,
        message_history=history,
        deps=deps,
        usage_limits=UsageLimits(request_limit=settings.agent_request_limit),
    )
    output = result.output

    if output.insufficient_evidence:
        return TurnResult(answer_text=output.answer, passages=[], citations=[], kind="insufficient")

    passages = validate_grounding(output, registry)  # raises GroundingError on a violation
    return TurnResult(
        answer_text=output.answer, passages=passages, citations=output.citations, kind="grounded"
    )
