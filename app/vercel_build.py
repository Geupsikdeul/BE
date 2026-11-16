"""Vercel build step ([tool.vercel.scripts] build): apply migrations, then create the
first admin from FIRST_ADMIN_* if set. Same as prestart.sh for Docker."""

import asyncio
import logging
import os
import sys

from alembic.config import Config

from alembic import command


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    if not os.environ.get("DATABASE_URL"):
        print("DATABASE_URL not set; skipping migrations")
        return
    command.upgrade(Config("alembic.ini"), "head")

    from app.db.init_db import main as init_db

    asyncio.run(init_db())


if __name__ == "__main__":
    sys.exit(main())
