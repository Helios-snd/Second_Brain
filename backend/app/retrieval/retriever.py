"""DocumentRetriever: one `.search()` call that hides both retrieval legs and
fusion behind a single client-like object — the same shape as querying a
Pinecone index, just backed by pgvector + Postgres FTS instead of a hosted
hybrid-search API.

No FastAPI route calls this yet; Phase 6's agent/orchestrator (not yet
built) is the intended caller, per docs/architecture.md's bounded-tool
design (`search_filings`, `read_chunk`, `read_surrounding_chunks`).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.database import documents
from app.database.models.document_chunk import DocumentChunk
from app.database.session import get_session_factory
from app.retrieval import embeddings, queries
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.types import RetrievedPassage, SearchFilters


def to_passage(
    chunk: DocumentChunk, score: float = 0.0, neighbors: list[RetrievedPassage] | None = None
) -> RetrievedPassage:
    """Build a `RetrievedPassage` from a `DocumentChunk` ORM row. `score` is the
    fusion score for a ranked hit, or 0.0 for a directly-read chunk / neighbor."""
    meta = chunk.chunk_metadata
    return RetrievedPassage(
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        chunk_index=chunk.chunk_index,
        text=chunk.chunk_text,
        page=chunk.page,
        section=chunk.section,
        fusion_score=score,
        ticker=meta["ticker"],
        company_name=meta.get("company_name"),
        filing_type=meta["filing_type"],
        filing_date=date.fromisoformat(meta["filing_date"]),
        fiscal_year=meta.get("fiscal_year"),
        accession_number=meta["accession_number"],
        neighbors=neighbors or [],
    )


class DocumentRetriever:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_factory = session_factory or get_session_factory()

    async def search(self, query: str, filters: SearchFilters | None = None) -> list[RetrievedPassage]:
        filters = filters or SearchFilters()
        query_embedding = embeddings.embed_query(query)

        async with self._session_factory() as session:
            # Sequential, not asyncio.gather: a single AsyncSession can't run
            # two statements concurrently (SQLAlchemy raises
            # "session is provisioning a new connection" if you try) — two
            # index-backed queries in a row is cheap enough that a second
            # session just to parallelize them isn't worth the complexity.
            semantic_hits = await queries.semantic_search(
                session, query_embedding, filters, settings.retrieval_candidate_k
            )
            fulltext_hits = await queries.fulltext_search(
                session, query, filters, settings.retrieval_candidate_k
            )
            fused = reciprocal_rank_fusion(
                [[h.chunk_id for h in semantic_hits], [h.chunk_id for h in fulltext_hits]],
                k=settings.retrieval_rrf_k,
            )[: settings.retrieval_top_k]

            chunks_by_id = await documents.get_chunks_by_ids(session, [chunk_id for chunk_id, _ in fused])

            passages: list[RetrievedPassage] = []
            for chunk_id, score in fused:
                chunk = chunks_by_id.get(chunk_id)
                if chunk is None:
                    continue  # hydration lost the race with a concurrent delete — skip, don't crash
                neighbor_rows = await documents.get_surrounding_chunks(
                    session, chunk_id, settings.retrieval_neighbor_radius
                )
                neighbors = [to_passage(n, 0.0) for n in neighbor_rows if n.id != chunk_id]
                passages.append(to_passage(chunk, score, neighbors))
            return passages
