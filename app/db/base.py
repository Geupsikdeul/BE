"""Import Base together with every model, so Base.metadata is complete.

Alembic (alembic/env.py) and the test setup import Base from here, never from base_class.
"""

from app.db.base_class import Base  # noqa: F401
from app.models import (  # noqa: F401
    AllowedStudent,
    MealCalendar,
    MealPoll,
    MealSignup,
    MealSignupSnapshot,
    PollOption,
    Student,
    Vote,
)
