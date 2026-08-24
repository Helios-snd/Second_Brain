# /// script
# requires-python = ">=3.12"
# dependencies = ["docling==2.120.1"]
# ///
"""Convert downloaded SEC filings (HTML) to Markdown with Docling.

Mirrors downloads/<year>/<file>.htm into markdown/<year>/<file>.md, and writes
a matching manifest.json so the Markdown corpus is discoverable the same way
the HTML corpus is.

Run with: uv run data/convert_to_markdown.py
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from docling import __version__ as docling_version
from docling.document_converter import DocumentConverter

DATA_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = DATA_DIR / "downloads"
MARKDOWN_DIR = DATA_DIR / "markdown"


def convert_filings() -> dict:
    manifest = json.loads((DOWNLOADS_DIR / "manifest.json").read_text(encoding="utf-8"))
    converter = DocumentConverter()

    markdown_manifest = {
        **manifest,
        "converted_at_utc": datetime.now(UTC).isoformat(),
        "converter": f"docling=={docling_version}",
        "filings": [],
    }

    for filing in manifest["filings"]:
        html_path = DOWNLOADS_DIR / filing["local_path"]
        markdown_path = (MARKDOWN_DIR / filing["local_path"]).with_suffix(".md")
        markdown_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"Converting {html_path.relative_to(DOWNLOADS_DIR)}...")
        result = converter.convert(html_path)
        markdown_path.write_text(result.document.export_to_markdown(), encoding="utf-8")

        markdown_manifest["filings"].append(
            {**filing, "local_path": str(markdown_path.relative_to(MARKDOWN_DIR))}
        )

    manifest_path = MARKDOWN_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(markdown_manifest, indent=2) + "\n", encoding="utf-8")
    return markdown_manifest


if __name__ == "__main__":
    result = convert_filings()
    print(f"Converted {len(result['filings'])} filing(s) to {MARKDOWN_DIR}")
    print(f"Manifest: {MARKDOWN_DIR / 'manifest.json'}")
