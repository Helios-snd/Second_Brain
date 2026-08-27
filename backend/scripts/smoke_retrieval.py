"""Manual smoke test for DocumentRetriever — prints ranked passages for a
question so you can eyeball relevance directly, without reading pytest
assertions.

Not a test: the automated version of this is
tests/retrieval/test_retriever_integration.py (`uv run pytest -m integration
tests/retrieval/`). Use this script for quick, ad-hoc checks against
whatever's currently in the DB — e.g. after an ingestion run adds a new
ticker, or while tuning retrieval_candidate_k / retrieval_rrf_k in config.py.

Hits the real Supabase Postgres DB and the real Gemini API (needs .env).

Run from backend/ with:
  uv run python scripts/smoke_retrieval.py "How has Apple's revenue mix shifted across its 2021-2025 10-Ks?"
  uv run python scripts/smoke_retrieval.py "NVIDIA Data Center demand drivers" --ticker NVDA
  uv run python scripts/smoke_retrieval.py "Azure capacity constraints" --ticker MSFT --fiscal-year 2024 --fiscal-year 2025
"""

from __future__ import annotations

import argparse
import asyncio

from app.retrieval.retriever import DocumentRetriever
from app.retrieval.types import SearchFilters


async def run(query: str, filters: SearchFilters) -> None:
    passages = await DocumentRetriever().search(query, filters=filters)

    if not passages:
        print("No passages returned.")
        return

    print(f'Query: "{query}"  filters={filters.model_dump(exclude_none=True)}\n')
    for i, p in enumerate(passages, start=1):
        print(
            f"[{i}] {p.ticker} {p.filing_type} FY{p.fiscal_year} chunk#{p.chunk_index} "
            f"section={p.section!r} score={p.fusion_score:.4f} neighbors={len(p.neighbors)}"
        )
        print("    " + p.text[:400].replace("\n", " "))
        print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("query", help="The question to retrieve passages for.")
    parser.add_argument("--ticker", default=None, help="Restrict to one ticker, e.g. AAPL.")
    parser.add_argument(
        "--fiscal-year",
        type=int,
        action="append",
        dest="fiscal_years",
        help="Restrict to a fiscal year (repeatable).",
    )
    parser.add_argument("--filing-type", default=None, help='Restrict to a filing type, e.g. "10-K".')
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    filters = SearchFilters(ticker=args.ticker, fiscal_years=args.fiscal_years, filing_type=args.filing_type)
    asyncio.run(run(args.query, filters))
