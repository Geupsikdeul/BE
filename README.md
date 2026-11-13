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
uv run uvicorn app.main:app --reload
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
app/
├── main.py              # FastAPI 앱 시작점 (CORS, 에러 핸들러, 라우터 연결)
├── api/                 # [HTTP 계층]
│   ├── deps.py          #   공통 의존성: DB, CurrentUser, require_admin
│   └── v1/
│       ├── router.py    #   /api/v1 아래로 엔드포인트 모음
│       └── endpoints/   #   실제 엔드포인트
│           ├── auth.py  health.py  polls.py  meals.py
│           └── admin/   #   /admin/* (라우터 단위로 require_admin 적용)
├── schemas/             # [입출력] Pydantic 요청/응답 스키마
├── crud/                # [DB 접근] 조회·저장 함수 (crud_student, crud_poll, crud_meal)
├── services/            # [규칙] DB와 무관한 판단 + 집계 (투표 상태, 신청 가능 여부, 마감 스냅샷)
├── models/              # [테이블] SQLAlchemy 모델
├── db/
│   ├── base_class.py    #   Base = DeclarativeBase
│   ├── base.py          #   Base + 모든 모델 import (Alembic / 테스트가 여기서 import)
│   ├── session.py       #   async 엔진, get_db
│   ├── types.py         #   UTCDateTime
│   └── init_db.py       #   초기 데이터 (FIRST_ADMIN_* 로 첫 관리자)
├── core/                # [공통 기반] config, security(JWT·해시), errors, clock
├── utils/utils.py       # 순수 헬퍼 (mask_name, pct)
└── cli.py               # 운영 명령 (create-admin, finalize-snapshots)
alembic/                 # 마이그레이션 (db/base.py 메타데이터로 autogenerate)
tests/
Dockerfile, prestart.sh  # 컨테이너: 시작 전 alembic upgrade head + init_db
```

Add a new resource by: SQLAlchemy model in `models/` (export it from `models/__init__.py` and `db/base.py`), schema in `schemas/`, DB functions in `crud/`, endpoint in `api/v1/endpoints/` (use the `DB` / `CurrentUser` deps from `api/deps.py`), then register it in `api/v1/router.py`. Run `alembic revision --autogenerate` to generate the migration.

## Docker

```bash
docker build -t geupsikdeul-backend .
docker run --env-file .env -p 8000:8000 geupsikdeul-backend
```

`prestart.sh` runs `alembic upgrade head` and `python -m app.db.init_db` before uvicorn starts. Set `FIRST_ADMIN_LOGIN` / `FIRST_ADMIN_PASSWORD` to create the first admin automatically. From inside a container, `DATABASE_URL` must point at a reachable host (not `localhost`).

## Operations

```bash
# First admin (teacher) account — prompts for password
uv run python -m app.cli create-admin --login teacher01 --name 홍길동

# Freeze meal counts whose deadline passed (meal_signup_snapshots). Run from cron, e.g. every 5 min.
# The admin summary endpoint also finalizes lazily on first read after the deadline.
uv run python -m app.cli finalize-snapshots
```

## Conventions

- Errors: `{"error": {"code", "message", "detail"}}` — codes in `core/errors.py`.
- `datetime` is UTC ISO 8601 (`...Z`); `date` is a KST calendar date. "Now" comes from `core/clock.py` only.
- `/admin/*` is protected once at router level (`api/v1/endpoints/admin/__init__.py`).
- Votes never expose `(student, option)` pairs — only aggregates and participation.
