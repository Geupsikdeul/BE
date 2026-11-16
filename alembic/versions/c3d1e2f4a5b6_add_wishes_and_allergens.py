"""add wishes, wish likes, student allergies, meal allergens

Revision ID: c3d1e2f4a5b6
Revises: b6f597b625f6
Create Date: 2026-11-16 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3d1e2f4a5b6"
down_revision: str | Sequence[str] | None = "b6f597b625f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wishes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("menu_name", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column("emoji", sa.String(length=16), server_default="🍽️", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_wishes_student_id"), "wishes", ["student_id"], unique=False)
    op.create_table(
        "wish_likes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("wish_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["wish_id"], ["wishes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("wish_id", "student_id", name="uq_wish_likes_wish_student"),
    )
    op.create_index(op.f("ix_wish_likes_student_id"), "wish_likes", ["student_id"], unique=False)
    op.create_index(op.f("ix_wish_likes_wish_id"), "wish_likes", ["wish_id"], unique=False)
    op.add_column("students", sa.Column("allergies", sa.JSON(), nullable=True))
    op.add_column("meal_calendar", sa.Column("breakfast_allergens", sa.JSON(), nullable=True))
    op.add_column("meal_calendar", sa.Column("dinner_allergens", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("meal_calendar", "dinner_allergens")
    op.drop_column("meal_calendar", "breakfast_allergens")
    op.drop_column("students", "allergies")
    op.drop_index(op.f("ix_wish_likes_wish_id"), table_name="wish_likes")
    op.drop_index(op.f("ix_wish_likes_student_id"), table_name="wish_likes")
    op.drop_table("wish_likes")
    op.drop_index(op.f("ix_wishes_student_id"), table_name="wishes")
    op.drop_table("wishes")
