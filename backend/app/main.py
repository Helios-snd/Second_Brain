from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from postgrest.exceptions import APIError
from starlette.responses import JSONResponse

from app.api.chat import router as chat_router
from app.api.me import router as me_router
from app.config import settings

app = FastAPI(title="Document Copilot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(me_router)
app.include_router(chat_router)


@app.exception_handler(APIError)
async def supabase_api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": "Upstream database error"})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
