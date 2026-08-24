import pandas as pd

from ingest.chunking import _collapse_duplicate_columns, detect_sections


def test_detect_sections_tags_chunks_with_most_recent_item() -> None:
    chunks = [
        "UNITED STATES\nSECURITIES AND EXCHANGE COMMISSION\nFORM 10-K",
        "Item 1. Business\nWe design, manufacture, and market...",
        "more business narrative with no Item marker",
        "Item 1A. Risk Factors\nOur business is subject to risks...",
    ]

    assert detect_sections(chunks) == [
        None,
        "Item 1. Business",
        "Item 1. Business",
        "Item 1A. Risk Factors",
    ]


def test_detect_sections_takes_last_marker_when_several_share_a_chunk() -> None:
    # Docling's merge_peers can fold two short, adjacent items into one chunk.
    chunk = "Item 2. Properties\nOur headquarters...\nItem 3. Legal Proceedings\nWe are subject to..."

    assert detect_sections([chunk]) == ["Item 3. Legal Proceedings"]


def test_detect_sections_strips_triplet_table_punctuation() -> None:
    # Some filings render the Item heading inside a table cell, which comes
    # through the triplet table serializer as "Item 1.,  = Business".
    chunk = "Item 1.,  = Business"

    assert detect_sections([chunk]) == ["Item 1. Business"]


def test_collapse_duplicate_columns_merges_a_genuine_colspan() -> None:
    # A row-label cell spanning 3 grid columns comes through as the same
    # value repeated in all 3 -- these should collapse to one column.
    df = pd.DataFrame(
        [["Americas", "Americas", "Americas", "167,045"]],
        columns=["", "", "", ""],
    )

    result = _collapse_duplicate_columns(df)

    assert result.shape == (1, 2)
    assert result.iloc[0].tolist() == ["Americas", "167,045"]


def test_collapse_duplicate_columns_never_merges_disagreeing_values() -> None:
    # Regression test: a table where every column has a blank header but
    # rows hold genuinely different data must NOT be collapsed into one
    # column -- an earlier version of this heuristic grouped purely by
    # header equality and silently discarded 29 of 30 columns here.
    df = pd.DataFrame(
        [
            ["2024", "", "Change", "", "2023"],
            ["Americas", "167,045", "3", "%", "162,560"],
        ],
        columns=["", "", "", "", ""],
    )

    result = _collapse_duplicate_columns(df)

    assert result.shape[1] == df.shape[1]
    assert result.iloc[1].tolist() == df.iloc[1].tolist()


def test_collapse_duplicate_columns_handles_empty_frame() -> None:
    assert _collapse_duplicate_columns(pd.DataFrame()).empty
