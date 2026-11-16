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


# 식품 알레르기 유발물질 표시 기준 (18종). 프론트·AI 모듈과 같은 표기를 쓴다.
ALLERGENS: tuple[str, ...] = (
    "달걀",
    "우유",
    "메밀",
    "땅콩",
    "대두",
    "밀",
    "고등어",
    "게",
    "새우",
    "돼지고기",
    "복숭아",
    "토마토",
    "아황산류",
    "호두",
    "닭고기",
    "쇠고기",
    "오징어",
    "조개류",
)
