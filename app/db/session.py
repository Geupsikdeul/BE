from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import ON_VERCEL, settings

# Serverless (Vercel): instances freeze between requests, so don't keep pooled connections.
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug and not ON_VERCEL,
    **({"poolclass": NullPool} if ON_VERCEL else {}),
)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
