from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import case, func, select

from geupsikdeul_backend.api.deps import DB
from geupsikdeul_backend.core import clock
from geupsikdeul_backend.core.errors import AppError
from geupsikdeul_backend.models import MealPoll, PollOption, Student, Vote
from geupsikdeul_backend.models.enums import PollStatus, Role
from geupsikdeul_backend.schemas.common import Page, PageParams
from geupsikdeul_backend.schemas.poll import (
    AdminPollRead,
    GradeParticipation,
    NonVoter,
    NonVoterList,
    OptionCount,
    PollCreate,
    PollOptionCreate,
    PollOptionRead,
    PollStats,
    PollUpdate,
)
from geupsikdeul_backend.services.polls import (
    get_any_poll,
    option_counts,
    pct,
    poll_status,
    total_votes,
    total_votes_subquery,
)

router = APIRouter(prefix="/polls")


def _read(poll: MealPoll, votes: int) -> AdminPollRead:
    return AdminPollRead(
        id=poll.id,
        title=poll.title,
        description=poll.description,
        target_date=poll.target_date,
        opens_at=poll.opens_at,
        closes_at=poll.closes_at,
        status=poll_status(poll),
        is_published=poll.is_published,
        total_votes=votes,
        created_at=poll.created_at,
        options=[PollOptionRead.model_validate(o) for o in poll.options],
    )


def _check_options(options: list[PollOptionCreate]) -> None:
    if len(options) < 2:
        raise AppError("TOO_FEW_OPTIONS")


async def _reload(db: DB, poll_id: int) -> MealPoll:
    db.expire_all()
    return await get_any_poll(db, poll_id)


@router.get("", response_model=Page[AdminPollRead])
async def list_polls(db: DB, params: Annotated[PageParams, Depends()]) -> Page[AdminPollRead]:
    total = await db.scalar(select(func.count(MealPoll.id))) or 0
    rows = await db.execute(
        select(MealPoll, total_votes_subquery())
        .order_by(MealPoll.opens_at.desc(), MealPoll.id.desc())
        .offset(params.offset)
        .limit(params.size)
    )
    return Page[AdminPollRead].build([_read(p, v or 0) for p, v in rows], total, params)


@router.post("", response_model=AdminPollRead, status_code=201)
async def create_poll(db: DB, payload: PollCreate) -> AdminPollRead:
    if payload.closes_at <= payload.opens_at:
        raise AppError("INVALID_PERIOD")
    _check_options(payload.options)
    poll = MealPoll(
        title=payload.title,
        description=payload.description,
        target_date=payload.target_date,
        opens_at=payload.opens_at,
        closes_at=payload.closes_at,
        is_published=False,
        created_at=clock.now(),
        options=[PollOption(**o.model_dump()) for o in payload.options],
    )
    db.add(poll)
    await db.commit()
    return _read(await _reload(db, poll.id), 0)


@router.get("/{poll_id}", response_model=AdminPollRead)
async def get_poll(db: DB, poll_id: int) -> AdminPollRead:
    poll = await get_any_poll(db, poll_id)
    return _read(poll, await total_votes(db, poll.id))


@router.patch("/{poll_id}", response_model=AdminPollRead)
async def update_poll(db: DB, poll_id: int, payload: PollUpdate) -> AdminPollRead:
    poll = await get_any_poll(db, poll_id)
    data = payload.model_dump(exclude_unset=True)

    if "options" in data:
        if data["options"] is None:
            raise AppError("TOO_FEW_OPTIONS")
        if poll_status(poll) != PollStatus.scheduled or await total_votes(db, poll.id):
            raise AppError("POLL_ALREADY_STARTED")
        _check_options(payload.options or [])
        poll.options = [PollOption(**o.model_dump()) for o in payload.options or []]

    for field in ("title", "description", "target_date", "opens_at", "closes_at"):
        if field in data:
            if data[field] is None and field != "description":
                continue
            setattr(poll, field, data[field])
    if poll.closes_at <= poll.opens_at:
        raise AppError("INVALID_PERIOD")

    await db.commit()
    poll = await _reload(db, poll_id)
    return _read(poll, await total_votes(db, poll.id))


@router.post("/{poll_id}/publish", response_model=AdminPollRead)
async def publish_poll(db: DB, poll_id: int) -> AdminPollRead:
    poll = await get_any_poll(db, poll_id)
    poll.is_published = True
    await db.commit()
    return _read(poll, await total_votes(db, poll.id))


@router.post("/{poll_id}/close", response_model=AdminPollRead)
async def close_poll(db: DB, poll_id: int) -> AdminPollRead:
    poll = await get_any_poll(db, poll_id)
    now = clock.now()
    if poll_status(poll, now) != PollStatus.closed:
        poll.closes_at = now
        if poll.opens_at > now:  # closing a not-yet-started poll keeps the period valid
            poll.opens_at = now
        await db.commit()
    return _read(poll, await total_votes(db, poll.id))


@router.delete("/{poll_id}", status_code=204)
async def delete_poll(db: DB, poll_id: int) -> Response:
    poll = await get_any_poll(db, poll_id)
    if await total_votes(db, poll.id):
        raise AppError("POLL_HAS_VOTES")
    await db.delete(poll)
    await db.commit()
    return Response(status_code=204)


def _eligible():
    return (Student.role == Role.student, Student.is_active.is_(True))


@router.get("/{poll_id}/stats", response_model=PollStats)
async def poll_stats(db: DB, poll_id: int) -> PollStats:
    """Aggregates only. No API ever returns a (student, option) pair."""
    poll = await get_any_poll(db, poll_id)
    counts = await option_counts(db, poll.id)

    voted_case = case((Vote.id.is_not(None), 1), else_=0)
    rows = await db.execute(
        select(Student.grade, func.count(Student.id), func.sum(voted_case))
        .outerjoin(Vote, (Vote.student_id == Student.id) & (Vote.poll_id == poll.id))
        .where(*_eligible(), Student.grade.is_not(None))
        .group_by(Student.grade)
        .order_by(Student.grade)
    )
    by_grade = [
        GradeParticipation(grade=g, voted=v or 0, eligible=e, rate=pct(v or 0, e))
        for g, e, v in rows
    ]
    eligible = sum(g.eligible for g in by_grade)
    voted_eligible = sum(g.voted for g in by_grade)
    return PollStats(
        poll_id=poll.id,
        total_votes=sum(c for _, _, c in counts),
        eligible_students=eligible,
        participation_rate=pct(voted_eligible, eligible),
        by_option=[OptionCount(option_id=i, menu_name=n, vote_count=c) for i, n, c in counts],
        by_grade=by_grade,
    )


@router.get("/{poll_id}/non-voters", response_model=NonVoterList)
async def non_voters(
    db: DB, poll_id: int, grade: int | None = None, class_no: int | None = None
) -> NonVoterList:
    poll = await get_any_poll(db, poll_id)
    voted = select(Vote.student_id).where(Vote.poll_id == poll.id)
    conds = [*_eligible(), Student.id.not_in(voted)]
    if grade is not None:
        conds.append(Student.grade == grade)
    if class_no is not None:
        conds.append(Student.class_no == class_no)
    rows = await db.scalars(
        select(Student).where(*conds).order_by(Student.grade, Student.class_no, Student.student_no)
    )
    items = [
        NonVoter(student_no=s.student_no, name=s.name, grade=s.grade, class_no=s.class_no)
        for s in rows
    ]
    return NonVoterList(items=items, total=len(items))
