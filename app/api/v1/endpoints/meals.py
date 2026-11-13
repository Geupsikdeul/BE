from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.core import clock
from app.core.errors import AppError
from app.crud.crud_meal import calendar_map, upsert_signup
from app.models import MealSignup
from app.models.enums import MealType
from app.schemas.meal import (
    BulkResultItem,
    BulkSignupRequest,
    BulkSignupResponse,
    CalendarDay,
    CalendarResponse,
    SignupItem,
    SignupList,
    SignupRequest,
)
from app.services.meals import check_range, is_locked, slot_of, slot_view, validate_signup

router = APIRouter(tags=["meals"])

FromQ = Annotated[date, Query(alias="from", description="시작일 (KST 날짜)")]
ToQ = Annotated[date, Query(description="종료일. from으로부터 최대 14일")]


def _days(from_: date, to: date) -> list[date]:
    return [date.fromordinal(o) for o in range(from_.toordinal(), to.toordinal() + 1)]


@router.get("/meal-calendar", response_model=CalendarResponse, response_model_exclude_none=False)
async def meal_calendar(db: DB, user: CurrentUser, from_: FromQ, to: ToQ) -> CalendarResponse:
    check_range(from_, to)
    cals = await calendar_map(db, from_, to)
    items = []
    for day in _days(from_, to):
        cal = cals.get(day)
        items.append(
            CalendarDay(
                service_date=day,
                breakfast=slot_view(day, slot_of(day, cal, MealType.breakfast)),
                dinner=slot_view(day, slot_of(day, cal, MealType.dinner)),
            )
        )
    return CalendarResponse(items=items)


@router.get("/meal-signups", response_model=SignupList)
async def my_signups(db: DB, user: CurrentUser, from_: FromQ, to: ToQ) -> SignupList:
    check_range(from_, to)
    cals = await calendar_map(db, from_, to)
    rows = await db.scalars(
        select(MealSignup)
        .where(MealSignup.student_id == user.id, MealSignup.service_date.between(from_, to))
        .order_by(MealSignup.service_date, MealSignup.meal_type)
    )
    now = clock.now()
    items = []
    for s in rows:
        meal = MealType(s.meal_type)
        slot = slot_of(s.service_date, cals.get(s.service_date), meal)
        items.append(
            SignupItem(
                service_date=s.service_date,
                meal_type=meal,
                will_attend=s.will_attend,
                # Locked once the deadline passes, or if the meal was cancelled afterwards.
                is_locked=not slot.available or is_locked(slot, now),
                updated_at=s.updated_at,
            )
        )
    return SignupList(items=items)


@router.put("/meal-signups", response_model=SignupItem)
async def put_signup(db: DB, user: CurrentUser, payload: SignupRequest) -> SignupItem:
    cals = await calendar_map(db, payload.service_date, payload.service_date)
    slot = slot_of(payload.service_date, cals.get(payload.service_date), payload.meal_type)
    if code := validate_signup(payload.service_date, slot):
        raise AppError(code)
    updated_at = await upsert_signup(
        db, user.id, payload.service_date, payload.meal_type, payload.will_attend
    )
    await db.commit()
    return SignupItem(
        service_date=payload.service_date,
        meal_type=payload.meal_type,
        will_attend=payload.will_attend,
        is_locked=False,
        updated_at=updated_at,
    )


@router.put("/meal-signups/bulk", response_model=BulkSignupResponse)
async def put_signups_bulk(
    db: DB, user: CurrentUser, payload: BulkSignupRequest
) -> BulkSignupResponse:
    days = [s.service_date for s in payload.signups]
    cals = await calendar_map(db, min(days), max(days))
    results: list[BulkResultItem] = []
    # Partial success: each item validated independently; valid ones are written.
    for s in payload.signups:
        slot = slot_of(s.service_date, cals.get(s.service_date), s.meal_type)
        code = validate_signup(s.service_date, slot)
        if code is None:
            await upsert_signup(db, user.id, s.service_date, s.meal_type, s.will_attend)
            results.append(
                BulkResultItem(service_date=s.service_date, meal_type=s.meal_type, status="ok")
            )
        else:
            results.append(
                BulkResultItem(
                    service_date=s.service_date, meal_type=s.meal_type, status="error", code=code
                )
            )
    await db.commit()
    ok = sum(r.status == "ok" for r in results)
    return BulkSignupResponse(succeeded=ok, failed=len(results) - ok, results=results)
