# Geupsikdeul Backend

학교 급식 서비스 (급식 메뉴 투표 · 조식/석식 신청) API. FastAPI + PostgreSQL (SQLAlchemy async) backend.

## Stack

- **FastAPI** — web framework
- **SQLAlchemy 2.0 (async)** + **asyncpg** — ORM / Postgres driver
- **Alembic** — migrations
- **uv** — package/venv manager
- **pytest** / **ruff** — testing & linting

## Setup

```bash
uv sync
cp .env.example .env
```

### PostgreSQL

Start a local PostgreSQL with Docker:

```bash
docker compose up -d
```

Or point `DATABASE_URL` in `.env` at any PostgreSQL instance (local install, RDS, etc). Must use the `postgresql+asyncpg://` scheme.

### Migrations

```bash
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
```

## Run

```bash
uv run uvicorn geupsikdeul_backend.main:app --reload
```

- Swagger UI: http://localhost:8000/docs
- Health check: http://localhost:8000/api/v1/health

## Test / Lint

```bash
uv run pytest
uv run ruff check .
```

## Project layout

```
src/geupsikdeul_backend/
  main.py          # FastAPI app + lifespan
  core/config.py   # Settings (env vars via pydantic-settings)
  db/base.py       # Declarative Base
  db/session.py    # Async engine + session dependency (get_db)
  models/          # SQLAlchemy models
  schemas/         # Pydantic request/response schemas
  api/v1/          # Routers
alembic/           # Migration environment (autogenerates from db/base.py metadata)
```

Add a new resource by: SQLAlchemy model in `models/` (and export it from `models/__init__.py`), schema in `schemas/`, router in `api/v1/` (use the `DB` / `CurrentUser` deps from `api/deps.py`), then register it in `api/v1/router.py`. Run `alembic revision --autogenerate` to generate the migration.

## Operations

```bash
# First admin (teacher) account — prompts for password
uv run python -m geupsikdeul_backend.cli create-admin --login teacher01 --name 홍길동

# Freeze meal counts whose deadline passed (meal_signup_snapshots). Run from cron, e.g. every 5 min.
# The admin summary endpoint also finalizes lazily on first read after the deadline.
uv run python -m geupsikdeul_backend.cli finalize-snapshots
```

## Conventions

- Errors: `{"error": {"code", "message", "detail"}}` — codes in `core/errors.py`.
- `datetime` is UTC ISO 8601 (`...Z`); `date` is a KST calendar date. "Now" comes from `core/clock.py` only.
- `/admin/*` is protected once at router level (`api/v1/admin/__init__.py`).
- Votes never expose `(student, option)` pairs — only aggregates and participation.
