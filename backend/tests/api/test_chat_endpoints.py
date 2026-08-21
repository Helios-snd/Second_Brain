import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from supabase_auth.types import User

from app.auth.dependencies import get_current_user, get_db_client
from app.database import chats
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


async def test_stream_chat_persists_and_streams(monkeypatch: pytest.MonkeyPatch) -> None:
    thread_id = uuid.uuid4()
    inserted: list[dict[str, Any]] = []

    async def fake_fetch(_client: object, _thread_id: str) -> dict[str, Any]:
        return {"id": str(thread_id), "user_id": "user-1"}

    async def fake_insert_message(_client: object, **kwargs: Any) -> dict[str, Any]:
        inserted.append(kwargs)
        return {"id": kwargs["message_id"], **kwargs}

    async def fake_touch_thread(_client: object, _thread_id: str) -> None:
        return None

    monkeypatch.setattr(chats, "fetch_thread_as_user", fake_fetch)
    monkeypatch.setattr(chats, "insert_message", fake_insert_message)
    monkeypatch.setattr(chats, "touch_thread", fake_touch_thread)

    body = {
        "id": str(thread_id),
        "trigger": "submit-message",
        "messages": [
            {"id": "m1", "role": "user", "parts": [{"type": "text", "text": "Hello"}]},
        ],
    }

    async with await _client() as http, http.stream("POST", "/chat/stream", json=body) as response:
        assert response.status_code == 200
        assert response.headers["x-vercel-ai-ui-message-stream"] == "v1"
        raw = b"".join([chunk async for chunk in response.aiter_bytes()]).decode()

    assert raw.startswith("data: ")
    assert raw.rstrip().endswith("data: [DONE]")
    assert len(inserted) == 2
    assert inserted[0]["role"] == "user"
    assert inserted[0]["content"] == "Hello"
    assert inserted[1]["role"] == "assistant"


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
