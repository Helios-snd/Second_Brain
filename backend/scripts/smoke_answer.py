"""Manual smoke test for a full grounded turn — retrieve → agent → grounding —
so you can eyeball the answer, its [n] markers, and the cited passages.

Not a test: the automated version is
tests/assistant/test_agent_integration.py (`uv run pytest -m integration`).
Use this for ad-hoc checks against whatever's in the DB, e.g. after an
ingestion run or while tuning the instructions / retrieval config.

Hits the real Supabase Postgres DB and the real Gemini API (needs .env).

Run from backend/ with:
  uv run python scripts/smoke_answer.py "How has Apple's revenue mix shifted across its 2021-2025 10-Ks?"
"""

from __future__ import annotations

import argparse
import asyncio

from pydantic_ai import ModelHTTPError

from app.chat.orchestrator import run_turn
from app.grounding.validator import GroundingError


async def run(question: str) -> None:
    try:
        turn = await run_turn(user_id="smoke", thread_id="smoke", history=[], question=question)
    except GroundingError as exc:
        print(f"GROUNDING VIOLATION — turn rejected: {exc}")
        return
    except ModelHTTPError as exc:
        detail = "daily free-tier quota exhausted" if exc.status_code == 429 else exc.body
        print(f"Gemini unavailable ({exc.status_code}): {detail}")
        return

    print(f'Question: "{question}"')
    print(f"Outcome:  {turn.kind}\n")
    print(turn.answer_text)
    print()
    for passage in turn.passages:
        print(
            f"[{passage.citation_index}] {passage.ticker} {passage.filing_type} "
            f"FY{passage.fiscal_year} — {passage.section}"
        )
        print(f'    excerpt: "{passage.excerpt}"')
        print(f"    chunk:   {passage.chunk_id}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("question", help="The analyst question to answer.")
    asyncio.run(run(parser.parse_args().question))
