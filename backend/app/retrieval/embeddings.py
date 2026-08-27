"""Gemini query embedding for retrieval.

Deliberately self-contained rather than importing `backend/ingest/embed.py`:
`app/` is the service, `ingest/` is a directory of one-off scripts, and this
is ~15 lines duplicated once rather than a cross-boundary import between the
two. See `ingest/embed.py` for the document-embedding side (same client
config, same normalization) — the two must stay in sync by hand if either
changes (model, retry policy, output dimensions).

`RETRIEVAL_QUERY` vs. ingestion's `RETRIEVAL_DOCUMENT`: Gemini's retrieval
task types are asymmetric, tuned differently for the indexed side vs. the
search side. Non-3072-dim output isn't pre-normalized, so queries need the
same manual L2 normalization ingestion applies to documents, or cosine
distance against the HNSW index (`vector_cosine_ops`) is meaningless.
"""

from __future__ import annotations

import math
from functools import cache

from google import genai
from google.genai import types

from app.config import settings

TASK_TYPE_QUERY = "RETRIEVAL_QUERY"


@cache
def get_gemini_client() -> genai.Client:
    return genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(attempts=8, initial_delay=2.0, max_delay=120.0)
        ),
    )


def embed_query(text: str) -> list[float]:
    client = get_gemini_client()
    response = client.models.embed_content(
        model=settings.gemini_embedding_model,
        contents=[text],
        config={
            "task_type": TASK_TYPE_QUERY,
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
