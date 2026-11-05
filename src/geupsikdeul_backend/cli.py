"""Operational commands.

uv run python -m geupsikdeul_backend.cli create-admin --login teacher01 --name 홍길동
uv run python -m geupsikdeul_backend.cli finalize-snapshots   # run from cron every few minutes
"""

import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select

from geupsikdeul_backend.core.security import hash_password, is_strong_password
from geupsikdeul_backend.db.session import async_session_factory, engine
from geupsikdeul_backend.models import Student
from geupsikdeul_backend.models.enums import Role
from geupsikdeul_backend.services.meals import finalize_due_snapshots


async def create_admin(login: str, name: str) -> None:
    password = getpass.getpass("Password: ")
    if not is_strong_password(password):
        sys.exit("비밀번호는 8자 이상, 영문과 숫자를 포함해야 합니다.")
    async with async_session_factory() as db:
        if await db.scalar(select(Student.id).where(Student.student_no == login)):
            sys.exit(f"'{login}' already exists")
        db.add(
            Student(
                student_no=login, name=name, password_hash=hash_password(password), role=Role.admin
            )
        )
        await db.commit()
    print(f"admin '{login}' created")


async def finalize() -> None:
    async with async_session_factory() as db:
        print(f"snapshots created: {await finalize_due_snapshots(db)}")


async def _run(args: argparse.Namespace) -> None:
    try:
        if args.cmd == "create-admin":
            await create_admin(args.login, args.name)
        elif args.cmd == "finalize-snapshots":
            await finalize()
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="geupsikdeul_backend.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create-admin")
    p.add_argument("--login", required=True)
    p.add_argument("--name", required=True)
    sub.add_parser("finalize-snapshots")
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
