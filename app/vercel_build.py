"""Vercel build step ([tool.vercel.scripts] build): apply migrations, create the first admin
from FIRST_ADMIN_* if set, and insert demo data when SEED_DEMO=true. Same as prestart.sh for
Docker. Runs on Vercel's network, so it also works where the DB port is blocked locally."""

import asyncio
import logging
import os

from alembic.config import Config

from alembic import command


async def _seed() -> None:
    from app.db.seed_demo import seed_demo
    from app.db.session import async_session_factory, engine

    try:
        async with async_session_factory() as db:
            print(f"demo data added: {await seed_demo(db)}")
    finally:
        await engine.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    if not (os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_UNPOOLED")):
        print("DATABASE_URL not set; skipping migrations")
        return
    command.upgrade(Config("alembic.ini"), "head")

    from app.db.init_db import main as init_db

    asyncio.run(init_db())
    if os.environ.get("SEED_DEMO", "").lower() == "true":
        asyncio.run(_seed())


if __name__ == "__main__":
    main()
