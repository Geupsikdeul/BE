from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import settings
from app.core.errors import AppError
from app.models import MealCalendar, MealSignup, MealSignupSnapshot, Student
from app.models.enums import MealType, Role, UnavailableReason
from app.schemas.meal import GradeAttending, MealSlot, MealSummary

MAX_RANGE_DAYS = 14


def check_range(from_: date, to: date) -> None:
    if to < from_ or (to - from_).days > MAX_RANGE_DAYS:
        raise AppError(
            "VALIDATION_ERROR",
            {"fields": {"to": [f"to는 from 이후, 최대 {MAX_RANGE_DAYS}일 이내여야 합니다."]}},
        )


def selectable_from(service_date: date) -> date:
    return service_date - timedelta(days=settings.signup_open_days_before)


@dataclass
class Slot:
    available: bool
    deadline: datetime | None
    menu: str | None
    reason: str | None


def slot_of(day: date, cal: MealCalendar | None, meal: MealType) -> Slot:
    if cal is None:
        reason = UnavailableReason.weekend if day.weekday() >= 5 else UnavailableReason.no_service
        return Slot(False, None, None, reason)
    available = getattr(cal, f"{meal}_available")
    deadline = getattr(cal, f"{meal}_deadline")
    if not available or deadline is None:
        reason = getattr(cal, f"{meal}_reason") or (
            UnavailableReason.weekend if day.weekday() >= 5 else UnavailableReason.no_service
        )
        return Slot(False, None, None, reason)
    return Slot(True, deadline, getattr(cal, f"{meal}_menu"), None)


def slot_view(day: date, slot: Slot) -> MealSlot:
    if not slot.available:
        return MealSlot(available=False, reason=slot.reason)
    return MealSlot(
        available=True,
        selectable_from=selectable_from(day),
        deadline=slot.deadline,
        menu=slot.menu,
    )


def is_locked(slot: Slot, now: datetime | None = None) -> bool:
    now = now or clock.now()
    return slot.deadline is not None and now >= slot.deadline


def validate_signup(day: date, slot: Slot) -> str | None:
    """Return an error code, or None if the signup may be written now (KST rules)."""
    if not slot.available:
        return "MEAL_NOT_AVAILABLE"
    if clock.today_kst() < selectable_from(day):
        return "DATE_OUT_OF_RANGE"
    if is_locked(slot):
        return "SIGNUP_DEADLINE_PASSED"
    return None


# ---- admin summary ----


def _eligible_filter():
    return (Student.role == Role.student, Student.is_active.is_(True))


async def compute_summary(db: AsyncSession, day: date, meal: MealType) -> MealSummary:
    eligible = await db.scalar(select(func.count(Student.id)).where(*_eligible_filter())) or 0

    attend_sum = func.sum(case((MealSignup.will_attend.is_(True), 1), else_=0))
    rows = await db.execute(
        select(Student.grade, attend_sum.label("attending"), func.count(MealSignup.id))
        .join(Student, Student.id == MealSignup.student_id)
        .where(MealSignup.service_date == day, MealSignup.meal_type == meal.value)
        .where(*_eligible_filter())
        .group_by(Student.grade)
        .order_by(Student.grade)
    )
    by_grade: list[GradeAttending] = []
    attending = responded = 0
    for grade, att, cnt in rows:
        attending += att or 0
        responded += cnt
        if grade is not None:
            by_grade.append(GradeAttending(grade=grade, attending=att or 0))
    return MealSummary(
        attending=attending,
        not_attending=responded - attending,
        no_response=max(eligible - responded, 0),
        is_finalized=False,
        finalized_at=None,
        by_grade=by_grade,
    )


async def summary_for(
    db: AsyncSession, day: date, meal: MealType, cal: MealCalendar | None
) -> MealSummary | None:
    slot = slot_of(day, cal, meal)
    if not slot.available:
        return None

    snap = await db.get(MealSignupSnapshot, (day, meal.value))
    if snap is not None:
        return MealSummary(
            attending=snap.attending,
            not_attending=snap.not_attending,
            no_response=snap.no_response,
            is_finalized=True,
            finalized_at=snap.finalized_at,
            by_grade=[GradeAttending(**g) for g in snap.by_grade],
        )

    live = await compute_summary(db, day, meal)
    if is_locked(slot):
        # Signups are frozen after the deadline, so the first post-deadline count is the
        # final one. Persist it so the number given to the kitchen never changes.
        snap = MealSignupSnapshot(
            service_date=day,
            meal_type=meal.value,
            attending=live.attending,
            not_attending=live.not_attending,
            no_response=live.no_response,
            by_grade=[g.model_dump() for g in live.by_grade],
            finalized_at=slot.deadline,
        )
        db.add(snap)
        try:
            await db.commit()
        except IntegrityError:  # another request finalized it first — use the stored one
            await db.rollback()
            return await summary_for(db, day, meal, cal)
        live.is_finalized = True
        live.finalized_at = slot.deadline
    return live


async def finalize_due_snapshots(db: AsyncSession) -> int:
    """Create snapshots for every meal whose deadline has passed. Safe to run repeatedly
    (e.g. from cron: `python -m app.cli finalize-snapshots`)."""
    now = clock.now()
    created = 0
    cals = await db.scalars(
        select(MealCalendar).where(MealCalendar.service_date >= (now - timedelta(days=30)).date())
    )
    for cal in list(cals):
        for meal in MealType:
            slot = slot_of(cal.service_date, cal, meal)
            if not slot.available or not is_locked(slot, now):
                continue
            if await db.get(MealSignupSnapshot, (cal.service_date, meal.value)) is None:
                await summary_for(db, cal.service_date, meal, cal)
                created += 1
    return created
