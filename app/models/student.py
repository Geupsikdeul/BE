from datetime import datetime

from sqlalchemy import Boolean, Integer, String, false, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.db.types import UTCDateTime


class AllowedStudent(Base):
    """재학생 화이트리스트. 가입 가능한 학번/이름/학년/반."""

    __tablename__ = "allowed_students"

    student_no: Mapped[str] = mapped_column(String(5), primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    grade: Mapped[int] = mapped_column(Integer)
    class_no: Mapped[int] = mapped_column(Integer)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class Student(Base):
    """가입 계정 (학생 + 관리자). 관리자는 화이트리스트 없이 CLI로 생성."""

    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 학생은 5자리 학번, 관리자는 로그인 ID
    student_no: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(50))
    password_hash: Mapped[str] = mapped_column(String(255))
    grade: Mapped[int | None] = mapped_column(Integer, index=True)
    class_no: Mapped[int | None] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16), default="student", server_default="student")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    # Bumped on password change/reset/disable -> invalidates issued tokens.
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    privacy_agreed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())
