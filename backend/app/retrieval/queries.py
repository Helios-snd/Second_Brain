"""The two retrieval legs: pgvector semantic search and Postgres full-text
search over `document_chunks`. Each returns its results ordered best-first —
`fusion.py` only cares about rank position, not the raw scores here.

Filters (ticker/fiscal_year/filing_type) read `chunk_metadata`, not a join to
`source_documents` — see `DocumentChunk.chunk_metadata`'s docstring: filing
fields are denormalized onto every chunk specifically so retrieval doesn't
need that join.
"""

from __future__ import annotations

import re
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, String, bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models.document_chunk import EMBEDDING_DIMENSIONS
from app.retrieval.types import RankedChunkHit, SearchFilters

_WORD_RE = re.compile(r"[a-z0-9]+")


def to_or_tsquery(query_text: str) -> str:
    """Turn a natural-language question into an OR `tsquery` string.

    `websearch_to_tsquery` ANDs every term, so a full analyst question ("How did
    Apple's Services revenue change across its 2021-2025 10-Ks?") matches no
    single chunk and the full-text leg contributes nothing to the hybrid fusion.
    ORing the terms lets `ts_rank_cd` rank chunks by how many terms they hit,
    which is what RRF wants — and `retrieval_candidate_k` caps the pool.

    Postgres' `english` dictionary stems and drops stopwords itself, so this only
    splits to word tokens and drops 1-char noise. Returns `""` when nothing
    usable remains (the caller then skips the leg).
    """
    seen: dict[str, None] = {}
    for token in _WORD_RE.findall(query_text.lower()):
        if len(token) > 1:
            seen.setdefault(token, None)
    return " | ".join(seen)

_FILTER_CLAUSE = """
      AND (:ticker ::text IS NULL OR chunk_metadata ->> 'ticker' = :ticker ::text)
      AND (:fiscal_years ::text[] IS NULL OR chunk_metadata ->> 'fiscal_year' = ANY(:fiscal_years ::text[]))
      AND (:filing_type ::text IS NULL OR chunk_metadata ->> 'filing_type' = :filing_type ::text)
"""

_SEMANTIC_SQL = text(
    f"""
    SELECT id, 1 - (embedding <=> :query_vec) AS score
    FROM document_chunks
    WHERE embedding IS NOT NULL
    {_FILTER_CLAUSE}
    ORDER BY embedding <=> :query_vec
    LIMIT :limit
    """
).bindparams(
    bindparam("query_vec", type_=Vector(EMBEDDING_DIMENSIONS)),
    bindparam("fiscal_years", type_=ARRAY(String)),
)

_FTS_SQL = text(
    f"""
    SELECT id, ts_rank_cd(search_vector, query) AS score
    FROM document_chunks, to_tsquery(:fts_config, :query_text) query
    WHERE search_vector @@ query
    {_FILTER_CLAUSE}
    ORDER BY score DESC
    LIMIT :limit
    """
).bindparams(
    bindparam("fiscal_years", type_=ARRAY(String)),
)


def _filter_params(filters: SearchFilters) -> dict[str, object]:
    return {
        "ticker": filters.ticker,
        "fiscal_years": [str(year) for year in filters.fiscal_years] if filters.fiscal_years else None,
        "filing_type": filters.filing_type,
    }


def _hits_from_rows(rows: list[object]) -> list[RankedChunkHit]:
    return [
        RankedChunkHit(chunk_id=uuid.UUID(str(row.id)), rank=rank, score=float(row.score))
        for rank, row in enumerate(rows, start=1)
    ]


async def semantic_search(
    session: AsyncSession, query_embedding: list[float], filters: SearchFilters, limit: int
) -> list[RankedChunkHit]:
    """Cosine similarity via the HNSW index (`ix_document_chunks_embedding_hnsw`,
    `vector_cosine_ops`) — `query_embedding` must already be L2-normalized
    (see `embeddings.embed_query`), matching how document embeddings are stored."""
    result = await session.execute(
        _SEMANTIC_SQL, {"query_vec": query_embedding, "limit": limit, **_filter_params(filters)}
    )
    return _hits_from_rows(result.all())


async def fulltext_search(
    session: AsyncSession, query_text: str, filters: SearchFilters, limit: int
) -> list[RankedChunkHit]:
    """Ranked full-text search via the GIN index (`ix_document_chunks_search_vector`)
    on the generated `search_vector` column. The question is turned into an OR
    `tsquery` by `to_or_tsquery` — see there for why AND (the
    `websearch_to_tsquery` default) makes this leg dead weight."""
    tsquery = to_or_tsquery(query_text)
    if not tsquery:
        return []
    result = await session.execute(
        _FTS_SQL,
        {
            "query_text": tsquery,
            "fts_config": settings.retrieval_fts_config,
            "limit": limit,
            **_filter_params(filters),
        },
    )
    return _hits_from_rows(result.all())
