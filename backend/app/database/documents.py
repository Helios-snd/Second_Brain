"""Low-level `document_chunks`/`source_documents` lookups via the ORM.

No vector/tsvector operators here — those live in `app/retrieval/queries.py`
as raw SQL. These are plain PK/FK reads, so the ORM (`DocumentChunk`,
`SourceDocument` — previously only used for Alembic autogenerate; this is
their first runtime use) is the natural fit. `retriever.py` uses
`get_chunks_by_ids`/`get_surrounding_chunks` to hydrate a fused result;
`get_chunk_with_document` is for Phase 6's `read_chunk` tool.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.document_chunk import DocumentChunk
from app.database.models.source_document import SourceDocument


async def get_chunks_by_ids(session: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, DocumentChunk]:
    if not ids:
        return {}
    result = await session.execute(select(DocumentChunk).where(DocumentChunk.id.in_(ids)))
    return {chunk.id: chunk for chunk in result.scalars()}


async def get_surrounding_chunks(session: AsyncSession, chunk_id: uuid.UUID, radius: int) -> list[DocumentChunk]:
    """Chunks within `radius` of `chunk_id` in the same document, ordered by
    `chunk_index` (includes `chunk_id` itself)."""
    anchor = await session.get(DocumentChunk, chunk_id)
    if anchor is None:
        return []
    result = await session.execute(
        select(DocumentChunk)
        .where(
            DocumentChunk.document_id == anchor.document_id,
            DocumentChunk.chunk_index >= anchor.chunk_index - radius,
            DocumentChunk.chunk_index <= anchor.chunk_index + radius,
        )
        .order_by(DocumentChunk.chunk_index)
    )
    return list(result.scalars())


async def get_chunk_with_document(
    session: AsyncSession, chunk_id: uuid.UUID
) -> tuple[DocumentChunk, SourceDocument] | None:
    result = await session.execute(
        select(DocumentChunk, SourceDocument)
        .join(SourceDocument, DocumentChunk.document_id == SourceDocument.id)
        .where(DocumentChunk.id == chunk_id)
    )
    row = result.first()
    return (row[0], row[1]) if row is not None else None
