from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Query, Response
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, CurrentUser
from app.core import clock
from app.core.config import settings
from app.core.errors import AppError
from app.core.security import (
    create_token,
    decode_token,
    hash_password,
    is_strong_password,
    verify_password,
)
from app.crud import crud_student
from app.models import AllowedStudent, Student
from app.models.enums import Role
from app.schemas.auth import (
    LoginRequest,
    MeResponse,
    PasswordChangeRequest,
    RefreshRequest,
    SignupRequest,
    SignupResponse,
    StudentNoCheck,
    TokenResponse,
)
from app.utils.utils import mask_name

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_tokens(user: Student) -> TokenResponse:
    return TokenResponse(
        access_token=create_token(user.id, user.token_version, "access"),
        refresh_token=create_token(user.id, user.token_version, "refresh"),
        expires_in=settings.access_token_expire_minutes * 60,
    )


async def _registered(db: DB, student_no: str) -> bool:
    found = await db.scalar(select(Student.id).where(Student.student_no == student_no))
    return found is not None


@router.get("/check-student-no", response_model=StudentNoCheck)
async def check_student_no(
    db: DB, student_no: Annotated[str, Query(min_length=1, max_length=32)]
) -> StudentNoCheck:
    allowed = await db.get(AllowedStudent, student_no)
    if allowed is None:
        raise AppError("STUDENT_NOT_ALLOWED")
    if allowed.is_used or await _registered(db, student_no):
        raise AppError("STUDENT_ALREADY_REGISTERED")
    return StudentNoCheck(
        student_no=allowed.student_no,
        name=mask_name(allowed.name),
        grade=allowed.grade,
        class_no=allowed.class_no,
        available=True,
    )


@router.post("/signup", response_model=SignupResponse, status_code=201)
async def signup(db: DB, payload: SignupRequest) -> Student:
    if payload.privacy_agreed is not True:
        raise AppError("PRIVACY_NOT_AGREED")
    allowed = await db.get(AllowedStudent, payload.student_no)
    if allowed is None:
        raise AppError("STUDENT_NOT_ALLOWED")
    if allowed.name != payload.name.strip():
        raise AppError("STUDENT_NAME_MISMATCH")
    if allowed.is_used or await _registered(db, payload.student_no):
        raise AppError("STUDENT_ALREADY_REGISTERED")
    if not is_strong_password(payload.password):
        raise AppError("WEAK_PASSWORD")

    # grade / class_no always come from the whitelist, never from the client.
    student = Student(
        student_no=allowed.student_no,
        name=allowed.name,
        password_hash=hash_password(payload.password),
        grade=allowed.grade,
        class_no=allowed.class_no,
        role=Role.student,
        privacy_agreed_at=clock.now(),
        created_at=clock.now(),
    )
    db.add(student)
    allowed.is_used = True
    try:
        await db.commit()
    except IntegrityError:  # concurrent signup for the same student_no
        await db.rollback()
        raise AppError("STUDENT_ALREADY_REGISTERED") from None
    await db.refresh(student)
    return student


@router.post("/login", response_model=TokenResponse)
async def login(db: DB, payload: LoginRequest) -> TokenResponse:
    user = await crud_student.get_by_student_no(db, payload.student_no)
    now = clock.now()

    if user is not None and user.locked_until is not None and user.locked_until > now:
        raise AppError("TOO_MANY_ATTEMPTS")

    # Always run a hash verification, so a missing account costs the same time.
    if not verify_password(payload.password, user.password_hash if user else None):
        if user is not None:
            # Atomic increment so concurrent failures are all counted.
            failures = await db.scalar(
                update(Student)
                .where(Student.id == user.id)
                .values(failed_login_count=Student.failed_login_count + 1)
                .returning(Student.failed_login_count)
            )
            if failures is not None and failures >= settings.login_max_failures:
                await db.execute(
                    update(Student)
                    .where(Student.id == user.id)
                    .values(
                        failed_login_count=0,
                        locked_until=now + timedelta(minutes=settings.login_lock_minutes),
                    )
                )
            await db.commit()
        raise AppError("INVALID_CREDENTIALS")

    assert user is not None
    if not user.is_active:
        raise AppError("ACCOUNT_DISABLED")

    if user.failed_login_count or user.locked_until:
        user.failed_login_count = 0
        user.locked_until = None
        await db.commit()
    return _issue_tokens(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(db: DB, payload: RefreshRequest) -> TokenResponse:
    claims = decode_token(payload.refresh_token, "refresh")
    if claims is None:
        raise AppError("INVALID_TOKEN")
    user = await db.get(Student, int(claims["sub"]))
    if user is None or user.token_version != claims.get("ver"):
        raise AppError("INVALID_TOKEN")
    if not user.is_active:
        raise AppError("ACCOUNT_DISABLED")
    return _issue_tokens(user)


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUser) -> Student:
    return user


@router.patch("/password", status_code=204)
async def change_password(db: DB, user: CurrentUser, payload: PasswordChangeRequest) -> Response:
    if not verify_password(payload.current_password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS")
    if not is_strong_password(payload.new_password):
        raise AppError("WEAK_PASSWORD")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    user.token_version += 1  # revoke every issued token, incl. the caller's; client re-logs in
    await db.commit()
    return Response(status_code=204)
