from app.core.config import normalize_db_url


def test_hosted_postgres_url_is_converted_for_asyncpg():
    url = "postgres://u:p@ep-x.neon.tech/db?sslmode=require&channel_binding=require"
    assert normalize_db_url(url) == "postgresql+asyncpg://u:p@ep-x.neon.tech/db?ssl=require"
    assert normalize_db_url("postgresql://u@h/db") == "postgresql+asyncpg://u@h/db"


def test_other_urls_untouched():
    local = "postgresql+asyncpg://postgres:postgres@localhost:5432/geupsikdeul"
    assert normalize_db_url(local) == local
    assert normalize_db_url("sqlite+aiosqlite://") == "sqlite+aiosqlite://"
