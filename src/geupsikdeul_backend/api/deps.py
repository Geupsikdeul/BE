from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from geupsikdeul_backend.core.errors import AppError
from geupsikdeul_backend.core.security import decode_token
from geupsikdeul_backend.db.session import get_db
from geupsikdeul_backend.models import Student
from geupsikdeul_backend.models.enums import Role

DB = Annotated[AsyncSession, Depends(get_db)]

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    db: DB,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Student:
    if credentials is None:
        raise AppError("INVALID_TOKEN")
    payload = decode_token(credentials.credentials, "access")
    if payload is None:
        raise AppError("INVALID_TOKEN")
    user = await db.get(Student, int(payload["sub"]))
    if user is None or user.token_version != payload.get("ver"):
        raise AppError("INVALID_TOKEN")
    if not user.is_active:
        raise AppError("ACCOUNT_DISABLED")
    return user


CurrentUser = Annotated[Student, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> Student:
    if user.role != Role.admin:
        raise AppError("FORBIDDEN")
    return user
