from ingest.load_document_chunks import build_chunk_metadata, build_chunk_rows

FILING = {
    "ticker": "AAPL",
    "cik": "0000320193",
    "form": "10-K",
    "filing_date": "2024-11-01",
    "report_date": "2024-09-28",
    "accession_number": "0000320193-24-000123",
    "primary_document": "aapl-20240928.htm",
    "source_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm",
    "local_path": "2024/aapl_10-k_2024-11-01_0000320193-24-000123.md",
}


def test_build_chunk_metadata_denormalizes_filing_fields() -> None:
    metadata = build_chunk_metadata(FILING, section="Item 7. Management's Discussion")

    assert metadata == {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "filing_type": "10-K",
        "filing_date": "2024-11-01",
        "fiscal_year": 2024,
        "accession_number": "0000320193-24-000123",
        "source_url": FILING["source_url"],
        "section": "Item 7. Management's Discussion",
        "page": None,
    }


def test_build_chunk_metadata_fiscal_year_comes_from_report_date_not_filing_date() -> None:
    # filing_date is 2024-11-01 (the year Apple filed) but the fiscal year the
    # filing actually covers is report_date's year (2024) -- these happen to
    # match for this fixture, so use a filing where they'd diverge.
    filing = {**FILING, "filing_date": "2025-01-15", "report_date": "2024-09-28"}

    metadata = build_chunk_metadata(filing, section=None)

    assert metadata["fiscal_year"] == 2024


def test_build_chunk_rows_assigns_sequential_zero_based_index() -> None:
    rows = build_chunk_rows(
        document_id="doc-1",
        filing=FILING,
        chunk_texts=["first chunk", "second chunk", "third chunk"],
        sections=[None, "Item 1. Business", "Item 1. Business"],
    )

    assert [r["chunk_index"] for r in rows] == [0, 1, 2]
    assert [r["chunk_text"] for r in rows] == ["first chunk", "second chunk", "third chunk"]
    assert all(r["document_id"] == "doc-1" for r in rows)
    assert all(r["page"] is None for r in rows)
    assert [r["section"] for r in rows] == [None, "Item 1. Business", "Item 1. Business"]
    assert rows[1]["chunk_metadata"]["section"] == "Item 1. Business"


def test_build_chunk_rows_requires_matching_lengths() -> None:
    try:
        build_chunk_rows(document_id="doc-1", filing=FILING, chunk_texts=["only one"], sections=[])
    except ValueError:
        pass
    else:
        raise AssertionError("expected a ValueError for mismatched chunk_texts/sections lengths")
