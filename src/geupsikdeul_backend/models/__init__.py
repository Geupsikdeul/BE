"""Importing this package registers every model on Base.metadata (used by Alembic)."""

from geupsikdeul_backend.models.meal import MealCalendar, MealSignup, MealSignupSnapshot
from geupsikdeul_backend.models.poll import MealPoll, PollOption, Vote
from geupsikdeul_backend.models.student import AllowedStudent, Student

__all__ = [
    "AllowedStudent",
    "MealCalendar",
    "MealPoll",
    "MealSignup",
    "MealSignupSnapshot",
    "PollOption",
    "Student",
    "Vote",
]
