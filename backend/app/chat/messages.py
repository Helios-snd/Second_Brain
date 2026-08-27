"""Conversions between the AI SDK wire format and what the agent / persistence
layers need.

`to_history_and_prompt` reuses `VercelAIAdapter.load_messages` (already a
dependency) rather than re-deriving the AI SDK message grammar; it only adds the
split between prior history and the current user turn, which PydanticAI's
`agent.run(prompt, message_history=...)` wants separately.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai.messages import ModelMessage
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.ui.vercel_ai.request_types import TextUIPart, UIMessage

from app.assistant.outputs import SourcePassage

CITATION_PART_TYPE = "data-citation"


def _text_of(message: UIMessage) -> str:
    return "".join(part.text for part in message.parts if isinstance(part, TextUIPart))


def to_history_and_prompt(ui_messages: list[UIMessage]) -> tuple[list[ModelMessage], str]:
    """Prior turns as PydanticAI messages, plus the latest user message as the prompt."""
    if not ui_messages:
        raise ValueError("no messages in request")
    history = VercelAIAdapter.load_messages(ui_messages[:-1])
    return history, _text_of(ui_messages[-1])


def citation_parts(passages: list[SourcePassage]) -> list[dict[str, Any]]:
    """The `data-citation` payload — streamed as a `DataChunk` and stored on the
    assistant message so a history reload shows citations without new code."""
    return [
        {
            "citation_index": p.citation_index,
            "chunk_id": str(p.chunk_id),
            "excerpt": p.excerpt,
            "text": p.text,
            "ticker": p.ticker,
            "company_name": p.company_name,
            "filing_type": p.filing_type,
            "filing_date": p.filing_date.isoformat(),
            "fiscal_year": p.fiscal_year,
            "section": p.section,
        }
        for p in passages
    ]
