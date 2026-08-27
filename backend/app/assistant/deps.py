"""Runtime dependencies for the document agent.

`TurnRegistry` is the trust boundary: it accumulates every passage the agent
legitimately saw this turn (the orchestrator's seed search + every tool call),
and it's the only set of `chunk_id`s the grounding validator will accept in a
citation. The agent can't cite what it never retrieved.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.retrieval.retriever import DocumentRetriever
from app.retrieval.types import RetrievedPassage


class TurnRegistry:
    """Passages the agent is allowed to cite this turn, keyed by `chunk_id`."""

    def __init__(self) -> None:
        self._passages: dict[uuid.UUID, RetrievedPassage] = {}

    def register(self, passages: Iterable[RetrievedPassage]) -> None:
        for passage in passages:
            self._passages.setdefault(passage.chunk_id, passage)
            for neighbor in passage.neighbors:
                self._passages.setdefault(neighbor.chunk_id, neighbor)

    def get(self, chunk_id: uuid.UUID) -> RetrievedPassage | None:
        return self._passages.get(chunk_id)

    def __contains__(self, chunk_id: object) -> bool:
        return chunk_id in self._passages

    def __len__(self) -> int:
        return len(self._passages)


@dataclass
class DocumentAgentDeps:
    user_id: str
    thread_id: str
    retriever: DocumentRetriever
    session_factory: async_sessionmaker[AsyncSession]
    registry: TurnRegistry = field(default_factory=TurnRegistry)
