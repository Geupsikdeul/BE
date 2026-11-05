import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import geupsikdeul_backend.models  # noqa: F401
from geupsikdeul_backend.core import clock
from geupsikdeul_backend.core.config import settings
from geupsikdeul_backend.core.security import hash_password
from geupsikdeul_backend.db.base import Base
from geupsikdeul_backend.db.session import get_db
from geupsikdeul_backend.main import app
from geupsikdeul_backend.models import AllowedStudent, Student

API = "/api/v1"
PASSWORD = "Secure1234!"
_PW_HASH = hash_password(PASSWORD)


class FakeClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 9, 10, 5, 30, tzinfo=UTC)

    def set(self, iso: str) -> None:
        self.current = datetime.fromisoformat(iso.replace("Z", "+00:00"))

    def __call__(self) -> datetime:
        return self.current


@pytest.fixture
def fake_clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fc = FakeClock()
    monkeypatch.setattr(clock, "utcnow", fc)
    # Tests jump the clock by weeks; keep tokens alive unless a test opts back in.
    monkeypatch.setattr(settings, "access_token_expire_minutes", 60 * 24 * 365)
    return fc


# Default: in-memory SQLite. Set TEST_DATABASE_URL to run against Postgres, e.g.
# TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/geupsikdeul_test
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    if TEST_DATABASE_URL:
        engine = create_async_engine(TEST_DATABASE_URL)
    else:
        engine = create_async_engine(
            "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def client(session_factory, fake_clock) -> AsyncIterator[AsyncClient]:
    async def _get_db():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_db] = _get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def db(session_factory) -> AsyncIterator[AsyncSession]:
    async with session_factory() as s:
        yield s


async def make_student(
    db: AsyncSession,
    student_no: str,
    name: str = "김철수",
    grade: int = 1,
    class_no: int = 3,
    role: str = "student",
) -> Student:
    if role == "student":
        db.add(
            AllowedStudent(
                student_no=student_no, name=name, grade=grade, class_no=class_no, is_used=True
            )
        )
    s = Student(
        student_no=student_no,
        name=name,
        password_hash=_PW_HASH,
        grade=grade if role == "student" else None,
        class_no=class_no if role == "student" else None,
        role=role,
    )
    db.add(s)
    await db.commit()
    return s


async def login(client: AsyncClient, student_no: str) -> dict[str, str]:
    r = await client.post(
        f"{API}/auth/login", json={"student_no": student_no, "password": PASSWORD}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
async def student_headers(client, db) -> dict[str, str]:
    await make_student(db, "10312")
    return await login(client, "10312")


@pytest.fixture
async def admin_headers(client, db) -> dict[str, str]:
    await make_student(db, "teacher01", name="담임", role="admin")
    return await login(client, "teacher01")
