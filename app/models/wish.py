from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.db.types import UTCDateTime


class Wish(Base):
    """학생 희망 메뉴. 작성자는 API에서 'N학년 익명'으로만 노출한다."""

    __tablename__ = "wishes"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    menu_name: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(String(200))
    emoji: Mapped[str] = mapped_column(String(16), default="🍽️", server_default="🍽️")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class WishLike(Base):
    __tablename__ = "wish_likes"
    __table_args__ = (UniqueConstraint("wish_id", "student_id", name="uq_wish_likes_wish_student"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    wish_id: Mapped[int] = mapped_column(ForeignKey("wishes.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
