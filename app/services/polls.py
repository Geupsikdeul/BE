"""Poll rules that don't touch the DB."""

from datetime import datetime

from app.core import clock
from app.models import MealPoll
from app.models.enums import PollStatus


def poll_status(poll: MealPoll, now: datetime | None = None) -> PollStatus:
    now = now or clock.now()
    if now < poll.opens_at:
        return PollStatus.scheduled
    if now >= poll.closes_at:
        return PollStatus.closed
    return PollStatus.open
