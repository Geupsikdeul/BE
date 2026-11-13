from datetime import date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from app.models.enums import MealType, UnavailableReason


class MealSlot(BaseModel):
    available: bool
    reason: UnavailableReason | None = None
    selectable_from: date | None = None
    deadline: datetime | None = None
    menu: str | None = None


class CalendarDay(BaseModel):
    service_date: date
    breakfast: MealSlot
    dinner: MealSlot


class CalendarResponse(BaseModel):
    items: list[CalendarDay]


class SignupItem(BaseModel):
    service_date: date
    meal_type: MealType
    will_attend: bool
    is_locked: bool
    updated_at: datetime


class SignupList(BaseModel):
    items: list[SignupItem]


class SignupRequest(BaseModel):
    service_date: date
    meal_type: MealType
    will_attend: bool


class BulkSignupRequest(BaseModel):
    signups: list[SignupRequest] = Field(min_length=1, max_length=100)


class BulkResultItem(BaseModel):
    service_date: date
    meal_type: MealType
    status: Literal["ok", "error"]
    code: str | None = None


class BulkSignupResponse(BaseModel):
    succeeded: int
    failed: int
    results: list[BulkResultItem]


# ---- admin ----


class GradeAttending(BaseModel):
    grade: int
    attending: int


class MealSummary(BaseModel):
    attending: int
    not_attending: int
    no_response: int
    is_finalized: bool
    finalized_at: datetime | None
    by_grade: list[GradeAttending]


class DaySummary(BaseModel):
    service_date: date
    breakfast: MealSummary | None = None
    dinner: MealSummary | None = None


class CalendarEntryCreate(BaseModel):
    service_date: date
    breakfast_available: bool = False
    breakfast_deadline: AwareDatetime | None = None
    breakfast_menu: str | None = None
    breakfast_reason: UnavailableReason | None = None
    dinner_available: bool = False
    dinner_deadline: AwareDatetime | None = None
    dinner_menu: str | None = None
    dinner_reason: UnavailableReason | None = None


class CalendarEntryUpdate(BaseModel):
    breakfast_available: bool | None = None
    breakfast_deadline: AwareDatetime | None = None
    breakfast_menu: str | None = None
    breakfast_reason: UnavailableReason | None = None
    dinner_available: bool | None = None
    dinner_deadline: AwareDatetime | None = None
    dinner_menu: str | None = None
    dinner_reason: UnavailableReason | None = None


class CalendarEntryRead(CalendarEntryCreate):
    breakfast_deadline: datetime | None = None
    dinner_deadline: datetime | None = None


class CalendarEntryList(BaseModel):
    items: list[CalendarEntryRead]
