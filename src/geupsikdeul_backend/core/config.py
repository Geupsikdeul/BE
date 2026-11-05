from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Geupsikdeul Backend"
    debug: bool = True

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/geupsikdeul"

    # JWT — override JWT_SECRET_KEY in every real environment.
    jwt_secret_key: str = "dev-only-change-me-please-0123456789abcdef"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14

    # Login lockout
    login_max_failures: int = 5
    login_lock_minutes: int = 10

    # Only the real frontend origins. Env format: CORS_ORIGINS=["https://app.example.com"]
    cors_origins: list[str] = ["http://localhost:3000"]

    # Polls: allow students to change their choice until the poll closes (spec 3.4)
    allow_vote_change: bool = True

    # Meal signups: how many days before service_date selection opens (spec 4.1)
    signup_open_days_before: int = 14


settings = Settings()
