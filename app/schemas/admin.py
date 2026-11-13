from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.auth import StudentRead


class RowError(BaseModel):
    row: int
    reason: str


class AllowedStudentImportResult(BaseModel):
    inserted: int
    skipped: int
    errors: list[RowError]


class AllowedStudentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    student_no: str
    name: str
    grade: int
    class_no: int
    is_used: bool


class AdminStudentRead(StudentRead):
    is_active: bool
    must_change_password: bool
    created_at: datetime


class StudentStatusUpdate(BaseModel):
    is_active: bool


class PasswordResetResponse(BaseModel):
    student_no: str
    temporary_password: str
    must_change: bool
