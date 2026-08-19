# Backend

FastAPI service for Document Copilot. See [../CLAUDE.md](../CLAUDE.md) and [CLAUDE.md](CLAUDE.md) for conventions.

## Setup

```bash
cd backend
uv sync
cp .env.example .env   # fill in Supabase + Gemini credentials
```

## Run

```bash
uv run uvicorn app.main:app --reload
```

Health check: `curl http://127.0.0.1:8000/health` → `{"status":"ok"}`

## Manage dependencies

```bash
uv add <package>       # add a runtime dependency
uv add --dev <package> # add a dev-only dependency
uv remove <package>
```

Always pass `uv sync`/`uv add`/`uv remove` through `pyproject.toml` — don't hand-edit `uv.lock`.

## Tests

```bash
uv run pytest -m "not integration"
```

## Migrations

```bash
uv run alembic revision --autogenerate -m "message"
uv run alembic upgrade head
```
