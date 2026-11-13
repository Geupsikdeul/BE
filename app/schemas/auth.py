from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Role


class StudentNoCheck(BaseModel):
    student_no: str
    name: str
    grade: int
    class_no: int
    available: bool


class SignupRequest(BaseModel):
    student_no: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=50)
    # Strength is checked in the handler so it can return WEAK_PASSWORD (not VALIDATION_ERROR).
    password: str = Field(max_length=128)
    privacy_agreed: bool


class StudentRead(BaseModel):
    """Public account view. Never includes password_hash."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    student_no: str
    name: str
    grade: int | None
    class_no: int | None
    role: Role


class SignupResponse(StudentRead):
    created_at: datetime


class MeResponse(StudentRead):
    must_change_password: bool


class LoginRequest(BaseModel):
    student_no: str = Field(max_length=32)
    password: str = Field(max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(max_length=128)
