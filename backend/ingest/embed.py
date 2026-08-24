"""Gemini embedding calls for document_chunks ingestion.

`gemini-embedding-001` defaults to 3072-dim output; any other
`output_dimensionality` (we use 1536, matching the DB's `vector(1536)`
column) comes back **not** unit-normalized -- Google's docs are explicit
that non-3072 dimensions must be manually L2-normalized before use in
cosine-similarity search. `embed_document_chunk` does that normalization;
skipping it would silently degrade the HNSW cosine index.
"""

from __future__ import annotations

import math
from functools import cache

from google import genai
from google.genai import types

from app.config import settings

TASK_TYPE_DOCUMENT = "RETRIEVAL_DOCUMENT"
# Query-time embeddings (Phase 5 retrieval) must use RETRIEVAL_QUERY instead --
# Gemini's retrieval task types are asymmetric, tuned differently for the
# indexed side vs. the search side.


@cache
def get_gemini_client() -> genai.Client:
    # The SDK's retry logic is opt-in: with no retry_options, a 429 (rate
    # limit) raises immediately on the first attempt (verified against a
    # real ingestion run -- it crashed on the very first RESOURCE_EXHAUSTED
    # instead of backing off). A batch ingestion script has no latency
    # requirement, so retry generously rather than trying to hand-tune a
    # fixed delay against a per-key quota this code can't see.
    return genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(attempts=8, initial_delay=2.0, max_delay=120.0)
        ),
    )


def count_tokens(client: genai.Client, text: str) -> int:
    """Authoritative token count for one finished chunk, via the real API
    (free) for the actual embedding model -- not the offline proxy
    tokenizer HybridChunker used to decide chunk boundaries."""
    response = client.models.count_tokens(model=settings.gemini_embedding_model, contents=text)
    return response.total_tokens


def embed_document_chunk(client: genai.Client, text: str) -> list[float]:
    response = client.models.embed_content(
        model=settings.gemini_embedding_model,
        contents=[text],
        config={
            "task_type": TASK_TYPE_DOCUMENT,
            "output_dimensionality": settings.gemini_embedding_dimensions,
        },
    )
    values = response.embeddings[0].values
    return _l2_normalize(values)


def _l2_normalize(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in values))
    if norm == 0:
        return values
    return [v / norm for v in values]
