from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.db.types import UTCDateTime


class MealCalendar(Base):
    """날짜당 1행. 조식/석식 운영 여부, 마감 시각, 메뉴."""

    __tablename__ = "meal_calendar"

    service_date: Mapped[date] = mapped_column(Date, primary_key=True)

    breakfast_available: Mapped[bool] = mapped_column(Boolean, default=False)
    breakfast_deadline: Mapped[datetime | None] = mapped_column(UTCDateTime)
    breakfast_menu: Mapped[str | None] = mapped_column(Text)
    breakfast_reason: Mapped[str | None] = mapped_column(String(20))

    dinner_available: Mapped[bool] = mapped_column(Boolean, default=False)
    dinner_deadline: Mapped[datetime | None] = mapped_column(UTCDateTime)
    dinner_menu: Mapped[str | None] = mapped_column(Text)
    dinner_reason: Mapped[str | None] = mapped_column(String(20))


class MealSignup(Base):
    __tablename__ = "meal_signups"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "service_date", "meal_type", name="uq_meal_signups_student_date_meal"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    service_date: Mapped[date] = mapped_column(Date, index=True)
    meal_type: Mapped[str] = mapped_column(String(16))
    will_attend: Mapped[bool] = mapped_column(Boolean)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class MealSignupSnapshot(Base):
    """마감 시점 집계 고정값. 급식실에 전달한 숫자가 이후에도 변하지 않도록."""

    __tablename__ = "meal_signup_snapshots"

    service_date: Mapped[date] = mapped_column(Date, primary_key=True)
    meal_type: Mapped[str] = mapped_column(String(16), primary_key=True)
    attending: Mapped[int] = mapped_column(Integer)
    not_attending: Mapped[int] = mapped_column(Integer)
    no_response: Mapped[int] = mapped_column(Integer)
    by_grade: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    finalized_at: Mapped[datetime] = mapped_column(UTCDateTime)
