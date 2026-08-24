"""Chunk, embed, and load document_chunks for the converted SEC filing corpus.

Reads data/markdown/manifest.json, looks up each filing's source_documents
row (must already be loaded -- see load_source_documents.py), chunks its
Markdown with Docling's HybridChunker, embeds each chunk with Gemini, and
upserts into document_chunks keyed on (document_id, chunk_index).

Idempotent: a document already holding chunk rows is skipped entirely
(pass --force to re-chunk and re-embed it). Embedding costs money, so
--max-chunks caps the total number of chunks embedded in one run --
use --max-chunks 1 to smoke-test the whole pipeline against one real row
before running the full corpus.

Run from backend/ with:
  uv run python ingest/load_document_chunks.py --max-chunks 1
  uv run python ingest/load_document_chunks.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from app.database.supabase import get_service_client
from ingest import chunking
from ingest.embed import count_tokens, embed_document_chunk, get_gemini_client
from ingest.load_source_documents import COMPANY_NAMES

REPO_ROOT = Path(__file__).resolve().parents[2]
MARKDOWN_DIR = REPO_ROOT / "data" / "markdown"

DEFAULT_MAX_TOKENS_PER_CHUNK = 1024


def build_chunk_metadata(filing: dict[str, Any], section: str | None) -> dict[str, Any]:
    """The chunk_metadata JSONB blob: filing fields denormalized onto every
    chunk so retrieval doesn't need to join source_documents for citations."""
    return {
        "ticker": filing["ticker"],
        "company_name": COMPANY_NAMES[filing["ticker"]],
        "filing_type": filing["form"],
        "filing_date": filing["filing_date"],
        "fiscal_year": int(filing["report_date"][:4]),
        "accession_number": filing["accession_number"],
        "source_url": filing["source_url"],
        "section": section,
        "page": None,
    }


def build_chunk_rows(
    document_id: str,
    filing: dict[str, Any],
    chunk_texts: list[str],
    sections: list[str | None],
) -> list[dict[str, Any]]:
    """Pure row-shaping: everything except token_count and embedding, which
    require network calls and get filled in by the caller."""
    return [
        {
            "document_id": document_id,
            "chunk_index": i,
            "page": None,
            "section": section,
            "chunk_text": text,
            "chunk_metadata": build_chunk_metadata(filing, section),
        }
        for i, (text, section) in enumerate(zip(chunk_texts, sections, strict=True))
    ]


async def get_document_id(client: Any, accession_number: str) -> str:
    result = (
        await client.table("source_documents")
        .select("id")
        .eq("accession_number", accession_number)
        .single()
        .execute()
    )
    return result.data["id"]


async def has_existing_chunks(client: Any, document_id: str) -> bool:
    result = (
        await client.table("document_chunks")
        .select("id", count="exact")
        .eq("document_id", document_id)
        .limit(1)
        .execute()
    )
    return (result.count or 0) > 0


async def load_document_chunks(*, max_chunks: int | None, force: bool, tickers: list[str] | None) -> int:
    manifest = json.loads((MARKDOWN_DIR / "manifest.json").read_text(encoding="utf-8"))
    supabase = get_service_client()
    gemini = get_gemini_client()
    tokenizer = chunking.build_tokenizer(max_tokens=DEFAULT_MAX_TOKENS_PER_CHUNK)

    total_embedded = 0
    for filing in manifest["filings"]:
        if tickers and filing["ticker"] not in tickers:
            continue
        if max_chunks is not None and total_embedded >= max_chunks:
            break

        document_id = await get_document_id(supabase, filing["accession_number"])
        if not force and await has_existing_chunks(supabase, document_id):
            print(f"skip {filing['ticker']} {filing['accession_number']} (already chunked)")
            continue

        markdown_path = MARKDOWN_DIR / filing["local_path"]
        doc = chunking.convert_markdown(markdown_path)
        doc_chunks = chunking.chunk_document(doc, tokenizer)
        chunk_texts = [c.text for c in doc_chunks]
        sections = chunking.detect_sections(chunk_texts)
        rows = build_chunk_rows(document_id, filing, chunk_texts, sections)

        if max_chunks is not None:
            remaining = max_chunks - total_embedded
            rows = rows[:remaining]

        print(f"{filing['ticker']} {filing['accession_number']}: embedding {len(rows)} chunk(s)")
        for row in rows:
            row["token_count"] = count_tokens(gemini, row["chunk_text"])
            row["embedding"] = embed_document_chunk(gemini, row["chunk_text"])

        await supabase.table("document_chunks").upsert(rows, on_conflict="document_id,chunk_index").execute()
        total_embedded += len(rows)

    return total_embedded


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=None,
        help="Stop after embedding this many chunks total (use 1 for the single-chunk smoke test).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-chunk and re-embed documents that already have rows in document_chunks.",
    )
    parser.add_argument(
        "--ticker",
        action="append",
        help="Only process this ticker (repeatable). Default: all filings in the manifest.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    embedded = asyncio.run(load_document_chunks(max_chunks=args.max_chunks, force=args.force, tickers=args.ticker))
    print(f"Embedded and upserted {embedded} chunk(s).")
