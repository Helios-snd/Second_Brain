"""The PydanticAI document agent: bounded retrieval tools + a typed
`GroundedAnswer` output.

Modeled on daveebbelaar/ai-cookbook `knowledge/agentic-rag/6-production.py` —
tools return agent-readable strings (each passage headed by the `chunk_id` the
model must cite with), the answer is a structured object, and every tool call
registers what it retrieved into `ctx.deps.registry` so the grounding validator
can reject a citation the agent never actually saw.

Retrieval and grounding stay outside this module (see `app/retrieval/`,
`app/grounding/`) so they're testable without the LLM.
"""

from __future__ import annotations

import uuid
from functools import cache
from pathlib import Path

from google.genai import types
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.settings import ModelSettings

from app.assistant.deps import DocumentAgentDeps
from app.assistant.outputs import GroundedAnswer
from app.config import settings
from app.database import documents
from app.retrieval.retriever import to_passage
from app.retrieval.types import RetrievedPassage, SearchFilters

_INSTRUCTIONS = Path(__file__).with_name("instructions.md").read_text(encoding="utf-8")

_NO_RESULTS = "No passages matched. Try different search terms or drop a filter."


@cache
def _model() -> GoogleModel:
    # Retry transient Gemini 429/503s (common on the free tier under load). Kept
    # shorter than ingestion's policy (embeddings.py: attempts=8) — this is the
    # interactive path, so a few quick retries, not minutes of backoff. A *daily*
    # free-tier quota 429 won't clear within the retry window and surfaces as a
    # ModelHTTPError → HTTP 502 (see app/api/chat.py).
    return GoogleModel(
        settings.gemini_model,
        provider=GoogleProvider(
            api_key=settings.gemini_api_key,
            retry_options=types.HttpRetryOptions(attempts=3, initial_delay=1.0, max_delay=15.0),
        ),
    )


def _format_passage(passage: RetrievedPassage) -> str:
    header = (
        f"[chunk_id={passage.chunk_id}] {passage.ticker} {passage.filing_type} "
        f"FY{passage.fiscal_year or '?'}"
    )
    if passage.section:
        header += f" — {passage.section}"
    return f"{header}\n{passage.text}"


def _format_passages(passages: list[RetrievedPassage]) -> str:
    if not passages:
        return _NO_RESULTS
    return "\n\n".join(_format_passage(p) for p in passages)


agent = Agent[DocumentAgentDeps, GroundedAnswer](
    _model(),
    output_type=GroundedAnswer,
    deps_type=DocumentAgentDeps,
    instructions=_INSTRUCTIONS,
    model_settings=ModelSettings(temperature=settings.agent_temperature),
    retries=2,
)


@agent.tool
async def search_filings(
    ctx: RunContext[DocumentAgentDeps],
    query: str,
    ticker: str | None = None,
    fiscal_years: list[int] | None = None,
    filing_type: str | None = None,
) -> str:
    """Hybrid search over the SEC filing corpus. Optionally scope to a ticker
    (e.g. "AAPL"), one or more fiscal years, or a filing type (e.g. "10-K")."""
    filters = SearchFilters(ticker=ticker, fiscal_years=fiscal_years, filing_type=filing_type)
    passages = await ctx.deps.retriever.search(query, filters=filters)
    ctx.deps.registry.register(passages)
    return _format_passages(passages)


@agent.tool
async def read_chunk(ctx: RunContext[DocumentAgentDeps], chunk_id: uuid.UUID) -> str:
    """Read one chunk in full by its `chunk_id`."""
    async with ctx.deps.session_factory() as session:
        found = await documents.get_chunk_with_document(session, chunk_id)
    if found is None:
        return f"No chunk with id {chunk_id}."
    passage = to_passage(found[0])
    ctx.deps.registry.register([passage])
    return _format_passage(passage)


@agent.tool
async def read_surrounding_chunks(ctx: RunContext[DocumentAgentDeps], chunk_id: uuid.UUID) -> str:
    """Read the chunks immediately before and after `chunk_id` in the same
    filing, for context around a promising hit."""
    async with ctx.deps.session_factory() as session:
        rows = await documents.get_surrounding_chunks(
            session, chunk_id, settings.retrieval_neighbor_radius
        )
    if not rows:
        return f"No chunk with id {chunk_id}."
    passages = [to_passage(row) for row in rows]
    ctx.deps.registry.register(passages)
    return _format_passages(passages)
