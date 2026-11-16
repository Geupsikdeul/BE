"""Operational commands.

uv run python -m app.cli create-admin --login teacher01 --name 홍길동
uv run python -m app.cli finalize-snapshots   # run from cron every few minutes
uv run python -m app.cli seed-demo            # dev only (DEBUG=true): demo data for the frontend
"""

import argparse
import asyncio
import getpass
import sys

from app.core.config import settings
from app.core.security import is_strong_password
from app.crud import crud_student
from app.db.session import async_session_factory, engine
from app.services.meals import finalize_due_snapshots


async def create_admin(login: str, name: str) -> None:
    password = getpass.getpass("Password: ")
    if not is_strong_password(password):
        sys.exit("비밀번호는 8자 이상, 영문과 숫자를 포함해야 합니다.")
    async with async_session_factory() as db:
        if await crud_student.get_by_student_no(db, login):
            sys.exit(f"'{login}' already exists")
        await crud_student.create_admin(db, login, name, password)
    print(f"admin '{login}' created")


async def finalize() -> None:
    async with async_session_factory() as db:
        print(f"snapshots created: {await finalize_due_snapshots(db)}")


async def seed() -> None:
    if not settings.debug:
        sys.exit("seed-demo는 DEBUG=true(개발 환경)에서만 실행할 수 있습니다.")
    from app.db.seed_demo import seed_demo

    async with async_session_factory() as db:
        print(f"demo data added: {await seed_demo(db)}")
    print("student 10312 / demo1234, admin teacher01 / teacher1234")


async def _run(args: argparse.Namespace) -> None:
    try:
        if args.cmd == "create-admin":
            await create_admin(args.login, args.name)
        elif args.cmd == "finalize-snapshots":
            await finalize()
        elif args.cmd == "seed-demo":
            await seed()
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create-admin")
    p.add_argument("--login", required=True)
    p.add_argument("--name", required=True)
    sub.add_parser("finalize-snapshots")
    sub.add_parser("seed-demo")
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
