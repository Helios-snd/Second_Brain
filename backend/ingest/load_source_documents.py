"""Load the converted Markdown corpus (data/markdown) into source_documents.

Reads data/markdown/manifest.json, pairs each filing with its Markdown file,
and upserts it into Supabase via the service-role client (keyed on
accession_number, so this is safe to re-run after re-converting a filing).

Run from backend/ with: uv run python ingest/load_source_documents.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from app.database.supabase import get_service_client

REPO_ROOT = Path(__file__).resolve().parents[2]
MARKDOWN_DIR = REPO_ROOT / "data" / "markdown"

COMPANY_NAMES = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corporation",
    "NVDA": "NVIDIA Corporation",
    "AMZN": "Amazon.com, Inc.",
    "GOOGL": "Alphabet Inc.",
}


def build_rows(manifest: dict) -> list[dict[str, Any]]:
    rows = []
    for filing in manifest["filings"]:
        markdown_path = MARKDOWN_DIR / filing["local_path"]
        rows.append(
            {
                "ticker": filing["ticker"],
                "company_name": COMPANY_NAMES[filing["ticker"]],
                "filing_type": filing["form"],
                "filing_date": filing["filing_date"],
                "fiscal_year": int(filing["report_date"][:4]),
                "accession_number": filing["accession_number"],
                "source_url": filing["source_url"],
                "content_markdown": markdown_path.read_text(encoding="utf-8"),
            }
        )
    return rows


async def load_source_documents() -> list[dict[str, Any]]:
    manifest = json.loads((MARKDOWN_DIR / "manifest.json").read_text(encoding="utf-8"))
    rows = build_rows(manifest)

    client = get_service_client()
    result = (
        await client.table("source_documents")
        .upsert(rows, on_conflict="accession_number")
        .execute()
    )
    return result.data


if __name__ == "__main__":
    loaded = asyncio.run(load_source_documents())
    print(f"Upserted {len(loaded)} source document(s) into Supabase.")
