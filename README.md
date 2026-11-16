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

## Frontend 연동 (Geupsikdeul/FE)

```bash
uv run alembic upgrade head
uv run python -m app.cli seed-demo   # DEBUG=true일 때만. 학생 10312/demo1234, 관리자 teacher01/teacher1234
uv run uvicorn app.main:app --reload
```

FE는 `http://127.0.0.1:5500`에서 실행 (CORS 기본값에 포함). 프론트용으로 추가된 API:

- `GET /wishes`, `POST /wishes`, `POST /wishes/{id}/like` (토글), `DELETE /wishes/{id}` (본인), `DELETE /admin/wishes/{id}`
- `GET·PUT /auth/me/allergies` — `registered: false`(미등록)와 `[]`(없음) 구분
- `meal-calendar` 각 끼니에 `allergens` (관리자 일정 등록 시 `breakfast_allergens` / `dinner_allergens`)
- `GET /polls/{id}`에 `total_votes` (참여 인원만, 선택지별 집계는 마감 후 `/result`)

알레르기 표기는 `models/enums.py`의 `ALLERGENS` 18종으로 검증합니다.

## AI (Claude)

`app/ai/`는 [Geupsikdeul/AI](https://github.com/Geupsikdeul/AI)에서 옮겨온 코드입니다. 관리자 JWT로 보호되는 API:

| API | 기능 |
|---|---|
| `POST /admin/ai/wish-analysis` | 희망 메뉴 묶기·요약 |
| `POST /admin/ai/poll-candidates` | 공감·제안 수로 투표 후보 선정 (최근 식단과 겹치면 감점) |
| `POST /admin/ai/poll-recommendations` | 학생 알레르기 집계(5명 이상 성분만)를 고려한 새 메뉴 추천 |
| `GET /admin/ai/menu-catalog` | 식단 초안에 쓸 메뉴 ID 목록 |
| `POST /admin/ai/menu-draft` | 식단 초안 + 규칙 검사 (저장하지 않음) |

`ANTHROPIC_API_KEY`가 없으면 503 `AI_NOT_CONFIGURED`. 모델은 `AI_MODEL` (기본 `claude-haiku-5-5`).

## Vercel 배포

- Vercel이 `app/main.py`의 `app`을 자동 인식합니다. `vercel.json`은 함수 최대 실행 시간(60초, AI 호출용)만 지정.
- 빌드 단계(`[tool.vercel.scripts] build`)에서 `alembic upgrade head` + 첫 관리자 생성(`FIRST_ADMIN_*`)을 실행합니다.
- 필요한 환경변수: `DATABASE_URL`(Neon 등 `postgres://...` 그대로 넣어도 asyncpg 형식으로 변환), `JWT_SECRET_KEY`(필수, 없으면 기동 거부), `DEBUG=false`, `FIRST_ADMIN_LOGIN/NAME/PASSWORD`, `ANTHROPIC_API_KEY`(선택), `CORS_ORIGINS`(FE를 프록시로 붙이면 불필요).
- 서버리스에서는 커넥션 풀을 쓰지 않습니다(`NullPool`).

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
