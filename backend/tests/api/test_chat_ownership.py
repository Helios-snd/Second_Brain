import uuid

import pytest
from fastapi import HTTPException

from app.api.chat import _require_owned_thread
from app.database import chats

pytestmark = pytest.mark.anyio

_THREAD_ID = uuid.uuid4()


async def test_owned_thread_returns_row(monkeypatch: pytest.MonkeyPatch) -> None:
    row = {"id": str(_THREAD_ID), "user_id": "user-1"}

    async def fake_fetch(_client: object, _thread_id: str) -> dict[str, str]:
        return row

    monkeypatch.setattr(chats, "fetch_thread_as_user", fake_fetch)

    result = await _require_owned_thread(_THREAD_ID, client=object())

    assert result == row


async def test_thread_exists_but_not_owned_raises_403(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch(_client: object, _thread_id: str) -> None:
        return None

    async def fake_exists(_thread_id: str) -> bool:
        return True

    monkeypatch.setattr(chats, "fetch_thread_as_user", fake_fetch)
    monkeypatch.setattr(chats, "thread_exists_privileged", fake_exists)

    with pytest.raises(HTTPException) as exc_info:
        await _require_owned_thread(_THREAD_ID, client=object())

    assert exc_info.value.status_code == 403


async def test_thread_missing_raises_404(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch(_client: object, _thread_id: str) -> None:
        return None

    async def fake_exists(_thread_id: str) -> bool:
        return False

    monkeypatch.setattr(chats, "fetch_thread_as_user", fake_fetch)
    monkeypatch.setattr(chats, "thread_exists_privileged", fake_exists)

    with pytest.raises(HTTPException) as exc_info:
        await _require_owned_thread(_THREAD_ID, client=object())

    assert exc_info.value.status_code == 404
