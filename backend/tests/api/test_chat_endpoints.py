import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from supabase_auth.types import User

from app.api import chat as chat_api
from app.assistant.outputs import Citation, SourcePassage
from app.auth.dependencies import get_current_user, get_db_client
from app.chat.orchestrator import TurnResult
from app.database import chats
from app.grounding.validator import GroundingError
from app.main import app

pytestmark = pytest.mark.anyio

_USER = User.model_construct(id="user-1", email="analyst@example.com")


@pytest.fixture(autouse=True)
def _override_auth() -> Any:
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[get_db_client] = lambda: object()
    yield
    app.dependency_overrides.clear()


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_list_threads(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(UTC).isoformat()
    row = {"id": str(uuid.uuid4()), "title": "Test", "created_at": now, "updated_at": now}

    async def fake_list_threads(_client: object) -> list[dict[str, Any]]:
        return [row]

    monkeypatch.setattr(chats, "list_threads", fake_list_threads)

    async with await _client() as http:
        response = await http.get("/chat/threads")

    assert response.status_code == 200
    assert response.json() == [row]


async def test_create_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(UTC).isoformat()
    thread_id = uuid.uuid4()

    async def fake_create_thread(_client: object, *, user_id: str, title: str | None) -> dict[str, Any]:
        assert user_id == "user-1"
        assert title == "New thread"
        return {"id": str(thread_id), "title": title, "created_at": now, "updated_at": now}

    monkeypatch.setattr(chats, "create_thread", fake_create_thread)

    async with await _client() as http:
        response = await http.post("/chat/threads", json={"title": "New thread"})

    assert response.status_code == 200
    assert response.json()["id"] == str(thread_id)


async def test_get_thread_messages_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch(_client: object, _thread_id: str) -> None:
        return None

    async def fake_exists(_thread_id: str) -> bool:
        return False

    monkeypatch.setattr(chats, "fetch_thread_as_user", fake_fetch)
    monkeypatch.setattr(chats, "thread_exists_privileged", fake_exists)

    async with await _client() as http:
        response = await http.get(f"/chat/threads/{uuid.uuid4()}/messages")

    assert response.status_code == 404


async def test_get_thread_messages_forbidden(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch(_client: object, _thread_id: str) -> None:
        return None

    async def fake_exists(_thread_id: str) -> bool:
        return True

    monkeypatch.setattr(chats, "fetch_thread_as_user", fake_fetch)
    monkeypatch.setattr(chats, "thread_exists_privileged", fake_exists)

    async with await _client() as http:
        response = await http.get(f"/chat/threads/{uuid.uuid4()}/messages")

    assert response.status_code == 403


@pytest.fixture
def _stub_persistence(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    calls: dict[str, list[Any]] = {"messages": [], "citations": [], "touch": []}

    async def fake_fetch(_client: object, thread_id: str) -> dict[str, Any]:
        return {"id": thread_id, "user_id": "user-1"}

    async def fake_insert_message(_client: object, **kwargs: Any) -> dict[str, Any]:
        calls["messages"].append(kwargs)
        return {"id": kwargs["message_id"], **kwargs}

    async def fake_insert_citations(message_id: str, citations: list[dict[str, Any]]) -> None:
        calls["citations"].append((message_id, citations))

    async def fake_touch_thread(_client: object, thread_id: str) -> None:
        calls["touch"].append(thread_id)

    monkeypatch.setattr(chats, "fetch_thread_as_user", fake_fetch)
    monkeypatch.setattr(chats, "insert_message", fake_insert_message)
    monkeypatch.setattr(chats, "insert_citations", fake_insert_citations)
    monkeypatch.setattr(chats, "touch_thread", fake_touch_thread)
    return calls


def _body(thread_id: uuid.UUID, text: str = "How did Apple services revenue change?") -> dict[str, Any]:
    return {
        "id": str(thread_id),
        "trigger": "submit-message",
        "messages": [{"id": "m1", "role": "user", "parts": [{"type": "text", "text": text}]}],
    }


def _grounded_turn() -> TurnResult:
    chunk_id = uuid.uuid4()
    return TurnResult(
        answer_text="Services revenue rose to $96.2B [1].",
        passages=[
            SourcePassage(
                citation_index=1,
                chunk_id=chunk_id,
                excerpt="$96.2 billion",
                text="Services net sales were $96.2 billion.",
                ticker="AAPL",
                company_name="Apple Inc.",
                filing_type="10-K",
                filing_date=date(2024, 11, 1),
                fiscal_year=2024,
                section="Item 7",
            )
        ],
        citations=[Citation(citation_index=1, chunk_id=chunk_id, excerpt="$96.2 billion")],
        kind="grounded",
    )


async def test_stream_chat_grounded_persists_message_and_citations(
    monkeypatch: pytest.MonkeyPatch, _stub_persistence: dict[str, list[Any]]
) -> None:
    thread_id = uuid.uuid4()
    turn = _grounded_turn()

    async def fake_run_turn(**_kwargs: Any) -> TurnResult:
        return turn

    monkeypatch.setattr(chat_api, "run_turn", fake_run_turn)

    async with await _client() as http, http.stream("POST", "/chat/stream", json=_body(thread_id)) as response:
        assert response.status_code == 200
        assert response.headers["x-vercel-ai-ui-message-stream"] == "v1"
        raw = b"".join([chunk async for chunk in response.aiter_bytes()]).decode()

    assert raw.startswith("data: ")
    assert raw.rstrip().endswith("data: [DONE]")
    assert "data-citation" in raw

    messages = _stub_persistence["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["content"] == turn.answer_text
    assert any(p["type"] == "data-citation" for p in messages[1]["parts"])

    message_id, citations = _stub_persistence["citations"][0]
    assert message_id == messages[1]["message_id"]
    assert citations == [{"chunk_id": str(turn.citations[0].chunk_id), "excerpt": "$96.2 billion"}]
    assert _stub_persistence["touch"] == [str(thread_id)]


async def test_stream_chat_insufficient_evidence_persists_message_without_citations(
    monkeypatch: pytest.MonkeyPatch, _stub_persistence: dict[str, list[Any]]
) -> None:
    thread_id = uuid.uuid4()

    async def fake_run_turn(**_kwargs: Any) -> TurnResult:
        return TurnResult(
            answer_text="The corpus has no Tesla filings.", passages=[], citations=[], kind="insufficient"
        )

    monkeypatch.setattr(chat_api, "run_turn", fake_run_turn)

    async with await _client() as http, http.stream("POST", "/chat/stream", json=_body(thread_id)) as response:
        assert response.status_code == 200
        raw = b"".join([chunk async for chunk in response.aiter_bytes()]).decode()

    assert "data-citation" not in raw
    assert [m["role"] for m in _stub_persistence["messages"]] == ["user", "assistant"]
    assert _stub_persistence["citations"] == [(_stub_persistence["messages"][1]["message_id"], [])]


async def test_stream_chat_grounding_violation_streams_error_and_persists_nothing(
    monkeypatch: pytest.MonkeyPatch, _stub_persistence: dict[str, list[Any]]
) -> None:
    thread_id = uuid.uuid4()

    async def fake_run_turn(**_kwargs: Any) -> TurnResult:
        raise GroundingError("cited an unretrieved chunk")

    monkeypatch.setattr(chat_api, "run_turn", fake_run_turn)

    async with await _client() as http, http.stream("POST", "/chat/stream", json=_body(thread_id)) as response:
        assert response.status_code == 200
        raw = b"".join([chunk async for chunk in response.aiter_bytes()]).decode()

    assert '"type":"error"' in raw.replace(" ", "")
    assert raw.rstrip().endswith("data: [DONE]")
    # only the user message was inserted, before the turn ran
    assert [m["role"] for m in _stub_persistence["messages"]] == ["user"]
    assert _stub_persistence["citations"] == []


async def test_stream_chat_upstream_llm_error_returns_502(
    monkeypatch: pytest.MonkeyPatch, _stub_persistence: dict[str, list[Any]]
) -> None:
    from pydantic_ai import ModelHTTPError

    thread_id = uuid.uuid4()

    async def fake_run_turn(**_kwargs: Any) -> TurnResult:
        raise ModelHTTPError(status_code=503, model_name="gemini-2.5-flash", body="unavailable")

    monkeypatch.setattr(chat_api, "run_turn", fake_run_turn)

    async with await _client() as http:
        response = await http.post("/chat/stream", json=_body(thread_id))

    assert response.status_code == 502


async def test_stream_chat_invalid_body_returns_422() -> None:
    async with await _client() as http:
        response = await http.post("/chat/stream", json={"id": "not-a-uuid"})

    assert response.status_code == 422


async def test_stream_chat_malformed_thread_id_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    body = {
        "id": "not-a-uuid",
        "trigger": "submit-message",
        "messages": [{"id": "m1", "role": "user", "parts": [{"type": "text", "text": "Hello"}]}],
    }

    async with await _client() as http:
        response = await http.post("/chat/stream", json=body)

    assert response.status_code == 404
