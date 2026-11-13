import csv
import io
import re
from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import delete, func, select

from app.api.deps import DB, require_admin
from app.core.errors import AppError
from app.core.security import generate_temporary_password, hash_password
from app.models import AllowedStudent, Student
from app.models.enums import Role
from app.schemas.admin import (
    AdminStudentRead,
    AllowedStudentImportResult,
    AllowedStudentRead,
    PasswordResetResponse,
    RowError,
    StudentStatusUpdate,
)
from app.schemas.common import Page, PageParams

router = APIRouter()

STUDENT_NO_RE = re.compile(r"^\d{5}$")
REQUIRED_HEADER = ["student_no", "name", "grade", "class_no"]
MAX_CSV_BYTES = 2 * 1024 * 1024


class ImportMode(StrEnum):
    append = "append"
    replace = "replace"


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp949"):  # Excel on Korean Windows saves CSV as cp949
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise AppError("VALIDATION_ERROR", {"fields": {"file": ["UTF-8 또는 CP949 CSV여야 합니다."]}})


@router.post("/allowed-students", response_model=AllowedStudentImportResult)
async def import_allowed_students(
    db: DB,
    file: Annotated[UploadFile, File(description="CSV: student_no,name,grade,class_no")],
    mode: Annotated[ImportMode, Form()] = ImportMode.append,
) -> AllowedStudentImportResult:
    raw = await file.read(MAX_CSV_BYTES + 1)
    if len(raw) > MAX_CSV_BYTES:
        raise AppError("VALIDATION_ERROR", {"fields": {"file": ["파일이 너무 큽니다 (최대 2MB)."]}})
    reader = csv.reader(io.StringIO(_decode(raw)))
    header = [h.strip() for h in next(reader, [])]
    if header != REQUIRED_HEADER:
        raise AppError(
            "VALIDATION_ERROR",
            {"fields": {"file": [f"헤더는 {','.join(REQUIRED_HEADER)} 이어야 합니다."]}},
        )

    errors: list[RowError] = []
    parsed: dict[str, AllowedStudent] = {}
    for row_no, row in enumerate(reader, start=2):  # row 1 is the header
        if not any(c.strip() for c in row):
            continue
        if len(row) != 4:
            errors.append(RowError(row=row_no, reason="열 개수 오류"))
            continue
        student_no, name, grade, class_no = (c.strip() for c in row)
        if not STUDENT_NO_RE.match(student_no):
            errors.append(RowError(row=row_no, reason=f"학번 형식 오류: '{student_no}'"))
            continue
        if not name or len(name) > 50:
            errors.append(RowError(row=row_no, reason="이름 형식 오류"))
            continue
        if not (grade.isdigit() and class_no.isdigit()):
            errors.append(RowError(row=row_no, reason="학년/반은 숫자여야 합니다"))
            continue
        if student_no in parsed:
            errors.append(RowError(row=row_no, reason=f"파일 내 중복 학번: '{student_no}'"))
            continue
        parsed[student_no] = AllowedStudent(
            student_no=student_no, name=name, grade=int(grade), class_no=int(class_no)
        )

    if mode == ImportMode.replace:
        # Entries already used by a registered account are kept (the account still exists);
        # disable graduated accounts through PATCH /admin/students/{id}/status.
        await db.execute(delete(AllowedStudent).where(AllowedStudent.is_used.is_(False)))

    existing = set(
        await db.scalars(
            select(AllowedStudent.student_no).where(AllowedStudent.student_no.in_(parsed))
        )
    )
    inserted = 0
    for student_no, entry in parsed.items():
        if student_no in existing:
            continue
        db.add(entry)
        inserted += 1
    await db.commit()
    return AllowedStudentImportResult(
        inserted=inserted, skipped=len(parsed) - inserted, errors=errors
    )


@router.get("/allowed-students", response_model=Page[AllowedStudentRead])
async def list_allowed_students(
    db: DB,
    params: Annotated[PageParams, Depends()],
    grade: int | None = None,
    class_no: int | None = None,
    is_used: bool | None = None,
) -> Page[AllowedStudentRead]:
    conds = []
    if grade is not None:
        conds.append(AllowedStudent.grade == grade)
    if class_no is not None:
        conds.append(AllowedStudent.class_no == class_no)
    if is_used is not None:
        conds.append(AllowedStudent.is_used.is_(is_used))
    total = await db.scalar(select(func.count()).select_from(AllowedStudent).where(*conds)) or 0
    rows = await db.scalars(
        select(AllowedStudent)
        .where(*conds)
        .order_by(AllowedStudent.student_no)
        .offset(params.offset)
        .limit(params.size)
    )
    items = [AllowedStudentRead.model_validate(r) for r in rows]
    return Page[AllowedStudentRead].build(items, total, params)


@router.get("/students", response_model=Page[AdminStudentRead])
async def list_students(
    db: DB,
    params: Annotated[PageParams, Depends()],
    grade: int | None = None,
    class_no: int | None = None,
    is_active: bool | None = None,
    role: Annotated[Role | None, Query()] = Role.student,
) -> Page[AdminStudentRead]:
    conds = []
    if role is not None:
        conds.append(Student.role == role)
    if grade is not None:
        conds.append(Student.grade == grade)
    if class_no is not None:
        conds.append(Student.class_no == class_no)
    if is_active is not None:
        conds.append(Student.is_active.is_(is_active))
    total = await db.scalar(select(func.count(Student.id)).where(*conds)) or 0
    rows = await db.scalars(
        select(Student)
        .where(*conds)
        .order_by(Student.student_no)
        .offset(params.offset)
        .limit(params.size)
    )
    items = [AdminStudentRead.model_validate(r) for r in rows]
    return Page[AdminStudentRead].build(items, total, params)


async def _get_student(db: DB, student_id: int) -> Student:
    student = await db.get(Student, student_id)
    if student is None:
        raise AppError("NOT_FOUND", message="학생을 찾을 수 없습니다.")
    return student


@router.patch("/students/{student_id}/status", response_model=AdminStudentRead)
async def set_student_status(
    db: DB,
    student_id: int,
    payload: StudentStatusUpdate,
    admin: Annotated[Student, Depends(require_admin)],
) -> Student:
    student = await _get_student(db, student_id)
    if student.id == admin.id and not payload.is_active:
        raise AppError("FORBIDDEN", message="자기 자신의 계정은 비활성화할 수 없습니다.")
    if student.is_active != payload.is_active:
        student.is_active = payload.is_active
        if not payload.is_active:
            student.token_version += 1  # revoke issued tokens immediately
        await db.commit()
    return student


@router.post("/students/{student_id}/reset-password", response_model=PasswordResetResponse)
async def reset_password(db: DB, student_id: int) -> PasswordResetResponse:
    student = await _get_student(db, student_id)
    temp = generate_temporary_password()
    student.password_hash = hash_password(temp)
    student.must_change_password = True
    student.token_version += 1
    student.failed_login_count = 0
    student.locked_until = None
    await db.commit()
    return PasswordResetResponse(
        student_no=student.student_no, temporary_password=temp, must_change=True
    )
