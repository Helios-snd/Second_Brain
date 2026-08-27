"""Reciprocal Rank Fusion — combines multiple ranked ID lists into one ranking.

Ported from the hybrid-retrieval pattern (daveebbelaar/ai-cookbook): fuse by
*rank position*, not raw score. That's what makes this work at all here —
cosine similarity (semantic leg) and `ts_rank_cd` (full-text leg) live on
completely different scales, so summing raw scores across legs would be
meaningless. Rank position is comparable across any retriever.
"""

from __future__ import annotations

import uuid
from collections import defaultdict


def reciprocal_rank_fusion(rankings: list[list[uuid.UUID]], k: int = 60) -> list[tuple[uuid.UUID, float]]:
    """`rankings`: one ordered (best-first) chunk-id list per retrieval leg.

    Returns `(chunk_id, fused_score)` pairs sorted best-first. A chunk absent
    from a given leg simply doesn't contribute to that leg's sum — it isn't
    penalized beyond not being counted.
    """
    scores: dict[uuid.UUID, float] = defaultdict(float)
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)
