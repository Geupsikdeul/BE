import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-change-me-please-0123456789abcdef"
ON_VERCEL = bool(os.environ.get("VERCEL"))


def normalize_db_url(url: str) -> str:
    """Hosted Postgres (Neon/Vercel/Supabase) gives postgres://...?sslmode=require.
    asyncpg needs postgresql+asyncpg:// and ssl=require (no sslmode/channel_binding)."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+asyncpg://" + url[len(prefix) :]
    if not url.startswith("postgresql+asyncpg://"):
        return url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query.pop("channel_binding", None)
    if "sslmode" in query:
        mode = query.pop("sslmode")
        if mode != "disable":
            query["ssl"] = "require"
    return urlunsplit(parts._replace(query=urlencode(query)))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Geupsikdeul Backend"
    debug: bool = True

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/geupsikdeul"

    # JWT — override JWT_SECRET_KEY in every real environment.
    jwt_secret_key: str = DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14

    # Login lockout
    login_max_failures: int = 5
    login_lock_minutes: int = 10

    # Only the real frontend origins. Env format: CORS_ORIGINS=["https://app.example.com"]
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ]

    # Polls: allow students to change their choice until the poll closes (spec 3.4)
    allow_vote_change: bool = True

    # Meal signups: how many days before service_date selection opens (spec 4.1)
    signup_open_days_before: int = 14

    # AI (Claude). 키가 없으면 /admin/ai/* 는 503 AI_NOT_CONFIGURED
    anthropic_api_key: str | None = None
    ai_model: str = "claude-haiku-5-5"

    # First admin, created by db/init_db.py (prestart.sh) if all are set and it doesn't exist
    first_admin_login: str | None = None
    first_admin_name: str = "관리자"
    first_admin_password: str | None = None

    @field_validator("database_url")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        return normalize_db_url(v)

    @model_validator(mode="after")
    def _require_secret_on_vercel(self) -> "Settings":
        if ON_VERCEL and self.jwt_secret_key == DEV_JWT_SECRET:
            raise ValueError("JWT_SECRET_KEY must be set in the Vercel environment")
        return self


settings = Settings()
