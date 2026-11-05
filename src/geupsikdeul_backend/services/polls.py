from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from geupsikdeul_backend.core import clock
from geupsikdeul_backend.core.errors import AppError
from geupsikdeul_backend.models import MealPoll, PollOption, Vote
from geupsikdeul_backend.models.enums import PollStatus


def poll_status(poll: MealPoll, now: datetime | None = None) -> PollStatus:
    now = now or clock.now()
    if now < poll.opens_at:
        return PollStatus.scheduled
    if now >= poll.closes_at:
        return PollStatus.closed
    return PollStatus.open


async def get_published_poll(db: AsyncSession, poll_id: int) -> MealPoll:
    poll = await db.get(MealPoll, poll_id)
    if poll is None or not poll.is_published:
        raise AppError("POLL_NOT_FOUND")
    return poll


async def get_any_poll(db: AsyncSession, poll_id: int) -> MealPoll:
    poll = await db.get(MealPoll, poll_id)
    if poll is None:
        raise AppError("POLL_NOT_FOUND")
    return poll


def total_votes_subquery():
    return (
        select(func.count(Vote.id))
        .where(Vote.poll_id == MealPoll.id)
        .correlate(MealPoll)
        .scalar_subquery()
    )


async def total_votes(db: AsyncSession, poll_id: int) -> int:
    return await db.scalar(select(func.count(Vote.id)).where(Vote.poll_id == poll_id)) or 0


def option_counts_query(poll_id: int) -> Select:
    """Single GROUP BY query — no per-option COUNT (N+1)."""
    return (
        select(PollOption.id, PollOption.menu_name, func.count(Vote.id).label("vote_count"))
        .outerjoin(Vote, Vote.option_id == PollOption.id)
        .where(PollOption.poll_id == poll_id)
        .group_by(PollOption.id, PollOption.menu_name)
        .order_by(PollOption.id)
    )


async def option_counts(db: AsyncSession, poll_id: int) -> list[tuple[int, str, int]]:
    rows = await db.execute(option_counts_query(poll_id))
    return [(r.id, r.menu_name, r.vote_count) for r in rows]


def pct(part: int, whole: int) -> float:
    return round(part * 100 / whole, 1) if whole else 0.0
