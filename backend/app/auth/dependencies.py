"""FastAPI dependency that authenticates requests against Supabase Auth.

Every protected route depends on `get_current_user`, which verifies the
caller's `Authorization: Bearer <supabase_jwt>` against Supabase's Auth API
(authoritative — catches revocation/expiry) and rejects anything invalid
with 401 before any chat or retrieval work runs.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import AsyncClient, AuthApiError
from supabase_auth.types import User

from app.database.supabase import get_user_client

_bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> User:
    if credentials is None:
        raise _unauthorized()

    token = credentials.credentials
    try:
        response = await get_user_client(token).auth.get_user(token)
    except AuthApiError as exc:
        raise _unauthorized() from exc

    if response is None:
        raise _unauthorized()

    return response.user


async def get_db_client(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AsyncClient:
    """A Supabase client scoped to the caller's own token, so RLS applies as the
    caller. Depends on the same `_bearer_scheme` sub-dependency as
    `get_current_user` — FastAPI's per-request dependency cache means the
    Authorization header is only parsed once."""
    if credentials is None:
        raise _unauthorized()
    return get_user_client(credentials.credentials)
