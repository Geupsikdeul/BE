from datetime import date, datetime

from sqlalchemy import Boolean, Date, ForeignKey, String, Text, UniqueConstraint, false, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.types import UTCDateTime


class MealPoll(Base):
    __tablename__ = "meal_polls"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    target_date: Mapped[date] = mapped_column(Date)
    opens_at: Mapped[datetime] = mapped_column(UTCDateTime)
    closes_at: Mapped[datetime] = mapped_column(UTCDateTime)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())

    options: Mapped[list["PollOption"]] = relationship(
        back_populates="poll",
        cascade="all, delete-orphan",
        order_by="PollOption.id",
        lazy="selectin",
    )


class PollOption(Base):
    __tablename__ = "poll_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    poll_id: Mapped[int] = mapped_column(
        ForeignKey("meal_polls.id", ondelete="CASCADE"), index=True
    )
    menu_name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(500))

    poll: Mapped[MealPoll] = relationship(back_populates="options")


class Vote(Base):
    """student_id는 중복 투표 방지 전용. (학생, 선택지) 쌍은 어떤 API로도 반환하지 않는다
    (본인의 my_option_id 제외)."""

    __tablename__ = "votes"
    __table_args__ = (UniqueConstraint("poll_id", "student_id", name="uq_votes_poll_student"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    poll_id: Mapped[int] = mapped_column(ForeignKey("meal_polls.id", ondelete="CASCADE"))
    option_id: Mapped[int] = mapped_column(
        ForeignKey("poll_options.id", ondelete="CASCADE"), index=True
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    voted_at: Mapped[datetime] = mapped_column(UTCDateTime)
