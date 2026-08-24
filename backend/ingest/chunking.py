"""Docling-based chunking for SEC filings.

Converts an already-exported Markdown filing back into a DoclingDocument
(verified to round-trip tables correctly) and runs Docling's HybridChunker
over it, with two SEC-specific adjustments Docling doesn't handle out of
the box:

- Section detection: SEC EDGAR HTML never uses real <h1>-<h6> tags, so
  Docling's HTML backend detects zero headings in every filing in this
  corpus. HybridChunker's structural `headings` metadata is therefore
  always empty here. `detect_sections` scans chunk text for "Item N."
  markers instead.
- Table cleanup: Docling represents a colspanned cell by repeating its
  text into every grid column/row it spans. That's faithful to the
  source but reads as long runs of duplicate/blank triplets once
  serialized (verified against real 10-K segment tables).
  `DedupedTripletTableSerializer` collapses adjacent columns that share
  an identical header before building triplets.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

import pandas as pd
from docling.document_converter import DocumentConverter
from docling_core.transforms.chunker.doc_chunk import DocChunk
from docling_core.transforms.chunker.hierarchical_chunker import (
    ChunkingDocSerializer,
    ChunkingSerializerProvider,
    TripletTableSerializer,
)
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer
from docling_core.transforms.serializer.common import create_ser_result
from docling_core.types.doc import DoclingDocument, TableItem
from google.genai import local_tokenizer
from pydantic import ConfigDict

_ITEM_RE = re.compile(r"^Item\s+(\d{1,2}[A-Za-z]?)\.\s*([^\n]*)", re.MULTILINE)

_CONVERTER = DocumentConverter()


class GeminiTokenizer(BaseTokenizer):
    """Offline token counting for HybridChunker, approximated via the
    Gemini chat-model (Gemma3) SentencePiece vocab.

    `gemini-embedding-001` has no published offline tokenizer, so this is
    a proxy, not an exact match for it -- callers must keep `max_tokens`
    well under the embedding model's real 2048-token input limit to
    absorb the estimation error. The authoritative count used for
    storage comes from a real `count_tokens` API call per finished
    chunk (see embed.py), not from this class.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    tokenizer: Any
    max_tokens: int

    def count_tokens(self, text: str) -> int:
        return self.tokenizer.count_tokens(text).total_tokens

    def get_max_tokens(self) -> int:
        return self.max_tokens

    def get_tokenizer(self) -> Callable[[str], int]:
        # semchunk's chunkerify() accepts a plain token-counting callable
        # (Callable[[str], int]) as an alternative to a tiktoken/transformers
        # tokenizer object -- LocalTokenizer is neither, so this is the
        # documented compatible interface, not a workaround.
        return lambda text: self.tokenizer.count_tokens(text).total_tokens


def build_tokenizer(max_tokens: int = 1024) -> GeminiTokenizer:
    return GeminiTokenizer(
        tokenizer=local_tokenizer.LocalTokenizer(model_name="gemini-2.5-flash"),
        max_tokens=max_tokens,
    )


def _collapse_duplicate_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Merge adjacent columns that share an identical header AND never
    disagree on a value.

    Docling's table-structure model represents a colspanned cell by
    repeating its text into every grid column it spans, in both header
    and data rows -- so a genuine span shows up as adjacent columns with
    the same header where, per row, at most one of them is non-blank.
    That second condition matters: many of these SEC tables have a blank
    ("") header on *every* column (the real header text lands in the
    first data row instead, not in `column_header` cells Docling
    recognizes), which would otherwise make "same header" match the
    entire table and collapse genuinely different columns into one,
    silently discarding data. Requiring row-by-row agreement catches
    that case -- a table with 30 blank-headed but differing columns
    fails the check on the first row with two populated columns, so the
    group splits at that point instead of merging.
    """
    if df.empty:
        return df

    groups: list[list[int]] = []
    for i, col in enumerate(df.columns):
        prev_group = groups[-1] if groups else None
        same_header = prev_group is not None and df.columns[prev_group[0]] == col
        agrees_per_row = same_header and _columns_never_conflict(df, prev_group, i)
        if agrees_per_row:
            prev_group.append(i)
        else:
            groups.append([i])

    headers = [df.columns[group[0]] for group in groups]
    collapsed_series = [
        df.iloc[:, group]
        .apply(lambda row: next((v for v in row if str(v).strip()), ""), axis=1)
        .reset_index(drop=True)
        for group in groups
    ]
    result = pd.concat(collapsed_series, axis=1)
    result.columns = headers
    return result


def _columns_never_conflict(df: pd.DataFrame, group: list[int], candidate: int) -> bool:
    """Whether adding `candidate` to `group` still leaves at most one
    *distinct* non-blank value per row across the combined columns.

    Distinct, not "at most one non-blank cell": a genuine span usually
    repeats the identical value in every column it covers (e.g. a row
    label duplicated three times), not one filled cell plus blanks. What
    must never happen is two columns disagreeing within the same row --
    that's the signal real, independent columns got swept into the group
    by a coincidentally-blank shared header.
    """
    combined = df.iloc[:, [*group, candidate]]
    distinct_counts = combined.apply(lambda row: len({str(v).strip() for v in row if str(v).strip()}), axis=1)
    return bool((distinct_counts <= 1).all())


class DedupedTripletTableSerializer(TripletTableSerializer):
    """`TripletTableSerializer` with a column-dedup pass before serializing.

    Reimplements `serialize()` (docling_core has no extension point for
    just the DataFrame-acquisition step) to insert
    `_collapse_duplicate_columns` right after the raw DataFrame is built.
    Uses `TableItem._export_to_dataframe_with_options`, a private
    docling_core API -- if a docling-core upgrade renames or removes it,
    this will need updating; the rest of the method mirrors
    `docling_core.transforms.chunker.hierarchical_chunker.TripletTableSerializer.serialize`.
    """

    def serialize(self, *, item, doc_serializer, doc, **kwargs):  # noqa: ANN001
        if not isinstance(item, TableItem):
            return super().serialize(item=item, doc_serializer=doc_serializer, doc=doc, **kwargs)

        parts = []
        shared_visited = kwargs.get("visited")
        cap_res = doc_serializer.serialize_captions(item=item, **kwargs)
        if cap_res.text:
            parts.append(cap_res)

        if item.self_ref not in doc_serializer.get_excluded_refs(**kwargs):
            local_kwargs = {**kwargs, "visited": set(shared_visited)} if shared_visited is not None else kwargs
            table_df = _collapse_duplicate_columns(
                item._export_to_dataframe_with_options(doc, doc_serializer=doc_serializer, **local_kwargs)
            )
            table_text = self._dataframe_to_text(table_df)
            if table_text:
                if shared_visited is not None:
                    shared_visited.update(local_kwargs["visited"])
                parts.append(create_ser_result(text=table_text, span_source=item))

        text_res = "\n\n".join(r.text for r in parts)
        return create_ser_result(text=text_res, span_source=parts)

    @classmethod
    def _dataframe_to_text(cls, table_df: pd.DataFrame) -> str:
        if table_df.shape[0] == 0 and len(table_df.columns) > 0:
            return ". ".join(text for col in table_df.columns if (text := str(col).strip()))

        if table_df.shape[0] < 1 or table_df.shape[1] < 1:
            return ""

        if table_df.shape[1] == 1:
            col_name = str(table_df.iloc[0, 0]).strip()
            values = [str(val).strip() for val in table_df.iloc[1:, 0].to_list()]
            if values:
                return ". ".join(f"{col_name} = {val}" for val in values)
            return col_name

        triplet_df = table_df.copy()
        triplet_df.loc[-1] = triplet_df.columns
        triplet_df.index = triplet_df.index + 1
        triplet_df = triplet_df.sort_index()

        rows = [str(v).strip() for v in triplet_df.iloc[:, 0].to_list()]
        cols = [str(v).strip() for v in triplet_df.iloc[0, :].to_list()]
        nrows, ncols = triplet_df.shape

        table_text = ". ".join(
            f"{rows[i]}, {cols[j]} = {str(triplet_df.iloc[i, j]).strip()}"
            for i in range(1, nrows)
            for j in range(1, ncols)
        )
        return table_text or cls._flatten_table_text(table_df)


class SecFilingSerializerProvider(ChunkingSerializerProvider):
    def get_serializer(self, doc: DoclingDocument) -> ChunkingDocSerializer:
        return ChunkingDocSerializer(doc=doc, table_serializer=DedupedTripletTableSerializer())


def convert_markdown(markdown_path: Path) -> DoclingDocument:
    return _CONVERTER.convert(markdown_path).document


def chunk_document(doc: DoclingDocument, tokenizer: BaseTokenizer) -> list[DocChunk]:
    chunker = HybridChunker(tokenizer=tokenizer, serializer_provider=SecFilingSerializerProvider())
    return list(chunker.chunk(doc))


def detect_sections(chunk_texts: list[str]) -> list[str | None]:
    """Tag each chunk (in document order) with the most recent "Item N."
    marker seen so far, or None before the first one (cover page / TOC).

    Docling's `merge_peers` folds a section heading paragraph together
    with surrounding text (there's no structural heading to stop at), so
    a real "Item N." marker can land anywhere in a chunk, and short
    adjacent items (e.g. "Item 2." immediately followed by "Item 3.")
    often land in the same chunk together -- verified against a real
    filing, where matches appeared at offsets from 0 up to ~5000 within
    a chunk, never reliably near the start. Taking the *last* match in
    each chunk (matches are in document order within a chunk too) means
    a chunk holding several short items still ends up correctly tagged
    with the last one by the time the next chunk starts.

    This corpus's actual table of contents is a rendered table (Docling
    triplets), not plain "Item N." paragraph text, so it doesn't trigger
    spurious matches here -- verified: the first match across a real
    filing was the genuine "Item 1. Business" heading, not the TOC.
    A body paragraph that references another Item in passing ("as
    described in Item 1A. Risk Factors above") would still misfire if it
    happens to be the last match in its chunk; this is a best-effort
    heuristic, not a guarantee.
    """
    sections: list[str | None] = []
    current: str | None = None
    for text in chunk_texts:
        matches = list(_ITEM_RE.finditer(text))
        if matches:
            label = matches[-1].group(1)
            # Some filings render the Item heading inside a table cell, which
            # comes through the triplet table serializer as e.g.
            # "Item 1.,  = Business" -- strip that leftover punctuation.
            title = re.sub(r"^[,.\s=]+", "", matches[-1].group(2))
            current = f"Item {label}. {title}" if title else f"Item {label}."
        sections.append(current)
    return sections
