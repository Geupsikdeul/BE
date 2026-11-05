import csv
import io
from datetime import date
from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Body, Query, Response
from sqlalchemy import and_, select

from geupsikdeul_backend.api.deps import DB
from geupsikdeul_backend.core.errors import AppError
from geupsikdeul_backend.models import MealCalendar, MealSignup, Student
from geupsikdeul_backend.models.enums import MealType, Role
from geupsikdeul_backend.schemas.meal import (
    CalendarEntryCreate,
    CalendarEntryList,
    CalendarEntryRead,
    CalendarEntryUpdate,
    DaySummary,
)
from geupsikdeul_backend.services.meals import summary_for

router = APIRouter()

DateQ = Annotated[date, Query(description="급식 제공일 (KST 날짜)")]


@router.get("/meal-signups/summary", response_model=DaySummary)
async def meal_summary(
    db: DB, date_: Annotated[date, Query(alias="date")], meal_type: MealType | None = None
) -> DaySummary:
    cal = await db.get(MealCalendar, date_)
    meals = [meal_type] if meal_type else list(MealType)
    result = DaySummary(service_date=date_)
    for meal in meals:
        setattr(result, meal.value, await summary_for(db, date_, meal, cal))
    return result


class ExportFormat(StrEnum):
    csv = "csv"
    xlsx = "xlsx"


_STATUS_LABEL = {True: "식사", False: "결식", None: "미응답"}
_HEADER = ["학번", "이름", "학년", "반", "신청"]


@router.get("/meal-signups/export")
async def export_signups(
    db: DB,
    date_: Annotated[date, Query(alias="date")],
    meal_type: MealType,
    format: ExportFormat = ExportFormat.csv,
) -> Response:
    rows = await db.execute(
        select(
            Student.student_no,
            Student.name,
            Student.grade,
            Student.class_no,
            MealSignup.will_attend,
        )
        .outerjoin(
            MealSignup,
            and_(
                MealSignup.student_id == Student.id,
                MealSignup.service_date == date_,
                MealSignup.meal_type == meal_type.value,
            ),
        )
        .where(Student.role == Role.student, Student.is_active.is_(True))
        .order_by(Student.grade, Student.class_no, Student.student_no)
    )
    data = [[no, name, g, c, _STATUS_LABEL[att]] for no, name, g, c, att in rows]
    stem = f"{meal_type.value}_{date_:%Y%m%d}"

    if format == ExportFormat.xlsx:
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = stem
        ws.append(_HEADER)
        for r in data:
            ws.append(r)
        buf = io.BytesIO()
        wb.save(buf)
        return Response(
            content=buf.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{stem}.xlsx"'},
        )

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(_HEADER)
    writer.writerows(data)
    # utf-8-sig = UTF-8 with BOM, so Excel opens Korean text correctly.
    return Response(
        content=out.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{stem}.csv"'},
    )


def _validate_entry(e: CalendarEntryCreate | MealCalendar) -> None:
    for meal in MealType:
        if getattr(e, f"{meal}_available") and getattr(e, f"{meal}_deadline") is None:
            raise AppError(
                "VALIDATION_ERROR",
                {"fields": {f"{meal}_deadline": ["운영하는 급식에는 마감 시각이 필요합니다."]}},
            )


@router.get("/meal-calendar", response_model=CalendarEntryList)
async def list_calendar(db: DB, from_: Annotated[date, Query(alias="from")], to: date):
    rows = await db.scalars(
        select(MealCalendar)
        .where(MealCalendar.service_date.between(from_, to))
        .order_by(MealCalendar.service_date)
    )
    return CalendarEntryList(
        items=[CalendarEntryRead.model_validate(r, from_attributes=True) for r in rows]
    )


@router.post("/meal-calendar", response_model=CalendarEntryList, status_code=201)
async def upsert_calendar(
    db: DB,
    payload: Annotated[CalendarEntryCreate | list[CalendarEntryCreate], Body()],
) -> CalendarEntryList:
    """단건(객체) 또는 일괄(배열). 이미 있는 날짜는 덮어씁니다."""
    entries = payload if isinstance(payload, list) else [payload]
    if len({e.service_date for e in entries}) != len(entries):
        raise AppError("VALIDATION_ERROR", {"fields": {"service_date": ["날짜가 중복됩니다."]}})
    saved = []
    for e in entries:
        _validate_entry(e)
        saved.append(await db.merge(MealCalendar(**e.model_dump())))
    await db.commit()
    return CalendarEntryList(
        items=[CalendarEntryRead.model_validate(s, from_attributes=True) for s in saved]
    )


@router.patch("/meal-calendar/{service_date}", response_model=CalendarEntryRead)
async def update_calendar(
    db: DB, service_date: date, payload: CalendarEntryUpdate
) -> CalendarEntryRead:
    cal = await db.get(MealCalendar, service_date)
    if cal is None:
        raise AppError("NOT_FOUND", message="등록되지 않은 급식 일정입니다.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(cal, field, value)
    _validate_entry(cal)
    await db.commit()
    return CalendarEntryRead.model_validate(cal, from_attributes=True)
