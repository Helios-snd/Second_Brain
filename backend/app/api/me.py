from fastapi import APIRouter, Depends
from supabase_auth.types import User

from app.auth.dependencies import get_current_user

router = APIRouter()


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)) -> dict[str, str]:
    return {"id": user.id, "email": user.email or ""}
