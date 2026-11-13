from enum import StrEnum


class Role(StrEnum):
    student = "student"
    admin = "admin"


class MealType(StrEnum):
    breakfast = "breakfast"
    dinner = "dinner"


class PollStatus(StrEnum):
    scheduled = "scheduled"
    open = "open"
    closed = "closed"


class UnavailableReason(StrEnum):
    weekend = "weekend"
    holiday = "holiday"
    exam_period = "exam_period"
    no_service = "no_service"
