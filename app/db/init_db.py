"""Initial data. Run by prestart.sh after migrations.

Creates the first admin from FIRST_ADMIN_LOGIN / FIRST_ADMIN_NAME / FIRST_ADMIN_PASSWORD
when those are set and the account doesn't exist yet. Safe to run on every start.
"""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import is_strong_password
from app.crud import crud_student
from app.db.session import async_session_factory, engine

logger = logging.getLogger(__name__)


async def init_db(db: AsyncSession) -> None:
    login, password = settings.first_admin_login, settings.first_admin_password
    if not (login and password):
        logger.info("FIRST_ADMIN_* not set; skipping first admin")
        return
    if await crud_student.get_by_student_no(db, login):
        return
    if not is_strong_password(password):
        raise SystemExit("FIRST_ADMIN_PASSWORD must be 8+ chars with letters and digits")
    await crud_student.create_admin(db, login, settings.first_admin_name, password)
    logger.info("first admin '%s' created", login)


async def main() -> None:
    try:
        async with async_session_factory() as db:
            await init_db(db)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
