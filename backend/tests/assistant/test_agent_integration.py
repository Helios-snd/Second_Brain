"""Real Gemini + real corpus. Excluded from the fast suite.

Needs .env (Supabase + Gemini) and an ingested corpus. Per docs/todos.md the
corpus currently covers AAPL (FY21-25), MSFT (FY21-25), and NVDA FY25 — the
questions here stay within that.

Run: uv run pytest -m integration tests/assistant/
"""

import pytest

from app.chat.orchestrator import run_turn

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


async def test_apple_services_revenue_question_is_grounded() -> None:
    turn = await run_turn(
        user_id="it",
        thread_id="it",
        history=[],
        question="How did Apple's Services revenue change across its 2021-2025 10-Ks?",
    )

    assert turn.kind == "grounded"
    assert turn.passages
    assert all(p.ticker == "AAPL" for p in turn.passages)
    # every [n] marker resolves to a real cited passage
    assert {p.citation_index for p in turn.passages} == set(range(1, len(turn.passages) + 1))


async def test_out_of_corpus_question_reports_insufficient_evidence() -> None:
    turn = await run_turn(
        user_id="it",
        thread_id="it",
        history=[],
        question="What was Tesla's automotive gross margin in fiscal 2023?",
    )

    assert turn.kind == "insufficient"
    assert turn.passages == []


async def test_generative_ai_margin_causation_is_refused_or_hedged() -> None:
    turn = await run_turn(
        user_id="it",
        thread_id="it",
        history=[],
        question="Do the filings prove generative AI improved gross margins for Apple, Microsoft, or NVIDIA?",
    )

    # Either an honest "not enough evidence", or a grounded answer (grounding
    # already enforced inside run_turn) that doesn't claim proven causation.
    assert turn.kind in {"grounded", "insufficient"}
    if turn.kind == "grounded":
        assert "prove" not in turn.answer_text.lower()
