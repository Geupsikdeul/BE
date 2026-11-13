"""DB access for meal calendar and signups."""

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.models import MealCalendar, MealSignup
from app.models.enums import MealType


async def calendar_map(db: AsyncSession, from_: date, to: date) -> dict[date, MealCalendar]:
    rows = await db.scalars(
        select(MealCalendar).where(MealCalendar.service_date.between(from_, to))
    )
    return {r.service_date: r for r in rows}


async def upsert_signup(
    db: AsyncSession, student_id: int, day: date, meal: MealType, will_attend: bool
) -> datetime:
    """INSERT ... ON CONFLICT (student_id, service_date, meal_type) DO UPDATE."""
    now = clock.now()
    insert = postgresql.insert if db.bind.dialect.name == "postgresql" else sqlite.insert
    stmt = insert(MealSignup).values(
        student_id=student_id,
        service_date=day,
        meal_type=meal.value,
        will_attend=will_attend,
        updated_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["student_id", "service_date", "meal_type"],
        set_={"will_attend": stmt.excluded.will_attend, "updated_at": stmt.excluded.updated_at},
    )
    await db.execute(stmt)
    return now
