"""DB access for student/admin accounts."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models import Student
from app.models.enums import Role


async def get_by_student_no(db: AsyncSession, student_no: str) -> Student | None:
    return await db.scalar(select(Student).where(Student.student_no == student_no))


async def create_admin(db: AsyncSession, login: str, name: str, password: str) -> Student:
    admin = Student(
        student_no=login, name=name, password_hash=hash_password(password), role=Role.admin
    )
    db.add(admin)
    await db.commit()
    return admin
