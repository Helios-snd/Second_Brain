import uuid
from datetime import date

from pydantic_ai.ui.vercel_ai.request_types import UIMessage

from app.assistant.outputs import SourcePassage
from app.chat import messages


def _msg(role: str, text: str) -> UIMessage:
    return UIMessage(id=role, role=role, parts=[{"type": "text", "text": text, "state": "done"}])


def test_to_history_and_prompt_splits_last_user_message() -> None:
    ui = [
        _msg("user", "first question"),
        _msg("assistant", "first answer"),
        _msg("user", "second question"),
    ]

    history, prompt = messages.to_history_and_prompt(ui)

    assert prompt == "second question"
    # history carries the prior turn but not the current question
    flat = repr(history)
    assert "first question" in flat and "first answer" in flat
    assert "second question" not in flat


def test_to_history_and_prompt_single_message_has_empty_history() -> None:
    history, prompt = messages.to_history_and_prompt([_msg("user", "only question")])

    assert history == []
    assert prompt == "only question"


def test_citation_parts_shape() -> None:
    chunk_id = uuid.uuid4()
    passage = SourcePassage(
        citation_index=2,
        chunk_id=chunk_id,
        excerpt="an excerpt",
        text="full chunk text",
        ticker="MSFT",
        company_name="Microsoft Corporation",
        filing_type="10-K",
        filing_date=date(2024, 7, 30),
        fiscal_year=2024,
        section="Item 1A",
    )

    [part] = messages.citation_parts([passage])

    assert part == {
        "citation_index": 2,
        "chunk_id": str(chunk_id),
        "excerpt": "an excerpt",
        "text": "full chunk text",
        "ticker": "MSFT",
        "company_name": "Microsoft Corporation",
        "filing_type": "10-K",
        "filing_date": "2024-07-30",
        "fiscal_year": 2024,
        "section": "Item 1A",
    }
