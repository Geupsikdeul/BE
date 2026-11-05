from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, exists, func, select
from sqlalchemy.exc import IntegrityError

from geupsikdeul_backend.api.deps import DB, CurrentUser
from geupsikdeul_backend.core import clock
from geupsikdeul_backend.core.config import settings
from geupsikdeul_backend.core.errors import AppError
from geupsikdeul_backend.models import MealPoll, PollOption, Vote
from geupsikdeul_backend.models.enums import PollStatus
from geupsikdeul_backend.schemas.common import Page, PageParams
from geupsikdeul_backend.schemas.poll import (
    OptionResult,
    PollDetail,
    PollOptionRead,
    PollResult,
    PollStatusFilter,
    PollSummary,
    VoteRequest,
    VoteResponse,
)
from geupsikdeul_backend.services.polls import (
    get_published_poll,
    option_counts,
    pct,
    poll_status,
    total_votes_subquery,
)

router = APIRouter(prefix="/polls", tags=["polls"])


@router.get("", response_model=Page[PollSummary])
async def list_polls(
    db: DB,
    user: CurrentUser,
    params: Annotated[PageParams, Depends()],
    status: Annotated[PollStatusFilter, Query()] = PollStatusFilter.open,
) -> Page[PollSummary]:
    now = clock.now()
    conditions = [MealPoll.is_published.is_(True)]
    if status == PollStatusFilter.open:
        conditions += [MealPoll.opens_at <= now, MealPoll.closes_at > now]
    elif status == PollStatusFilter.closed:
        conditions.append(MealPoll.closes_at <= now)

    total = await db.scalar(select(func.count(MealPoll.id)).where(*conditions)) or 0

    has_voted = exists().where(and_(Vote.poll_id == MealPoll.id, Vote.student_id == user.id))
    rows = await db.execute(
        select(MealPoll, has_voted.label("has_voted"), total_votes_subquery().label("total"))
        .where(*conditions)
        .order_by(MealPoll.closes_at.desc(), MealPoll.id.desc())
        .offset(params.offset)
        .limit(params.size)
    )
    items = [
        PollSummary(
            id=p.id,
            title=p.title,
            target_date=p.target_date,
            opens_at=p.opens_at,
            closes_at=p.closes_at,
            status=poll_status(p, now),
            has_voted=bool(voted),
            total_votes=total or 0,
        )
        for p, voted, total in rows
    ]
    return Page[PollSummary].build(items, total, params)


@router.get("/{poll_id}", response_model=PollDetail)
async def get_poll(db: DB, user: CurrentUser, poll_id: int) -> PollDetail:
    poll = await get_published_poll(db, poll_id)
    # The student's own choice only. Per-option counts are never included here.
    my_option_id = await db.scalar(
        select(Vote.option_id).where(Vote.poll_id == poll.id, Vote.student_id == user.id)
    )
    return PollDetail(
        id=poll.id,
        title=poll.title,
        description=poll.description,
        target_date=poll.target_date,
        opens_at=poll.opens_at,
        closes_at=poll.closes_at,
        status=poll_status(poll),
        has_voted=my_option_id is not None,
        my_option_id=my_option_id,
        options=[PollOptionRead.model_validate(o) for o in poll.options],
    )


async def _validate_vote(db: DB, poll_id: int, option_id: int) -> MealPoll:
    poll = await get_published_poll(db, poll_id)
    if poll_status(poll) != PollStatus.open:
        raise AppError("POLL_NOT_OPEN")
    option_ok = await db.scalar(
        select(PollOption.id).where(PollOption.id == option_id, PollOption.poll_id == poll.id)
    )
    if option_ok is None:
        raise AppError("INVALID_OPTION")
    return poll


@router.post("/{poll_id}/vote", response_model=VoteResponse, status_code=201)
async def cast_vote(db: DB, user: CurrentUser, poll_id: int, payload: VoteRequest) -> VoteResponse:
    poll = await _validate_vote(db, poll_id, payload.option_id)
    vote = Vote(
        poll_id=poll.id, option_id=payload.option_id, student_id=user.id, voted_at=clock.now()
    )
    db.add(vote)
    try:
        # UNIQUE(poll_id, student_id) is the real guard; no check-then-insert.
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise AppError("VOTE_ALREADY_CAST") from None
    return VoteResponse(poll_id=vote.poll_id, option_id=vote.option_id, voted_at=vote.voted_at)


@router.put("/{poll_id}/vote", response_model=VoteResponse)
async def change_vote(
    db: DB, user: CurrentUser, poll_id: int, payload: VoteRequest
) -> VoteResponse:
    if not settings.allow_vote_change:
        raise AppError("VOTE_CHANGE_DISABLED")
    poll = await _validate_vote(db, poll_id, payload.option_id)
    vote = await db.scalar(
        select(Vote).where(Vote.poll_id == poll.id, Vote.student_id == user.id).with_for_update()
    )
    if vote is None:
        raise AppError("VOTE_NOT_FOUND")
    vote.option_id = payload.option_id
    vote.voted_at = clock.now()
    await db.commit()
    return VoteResponse(poll_id=vote.poll_id, option_id=vote.option_id, voted_at=vote.voted_at)


@router.get("/{poll_id}/result", response_model=PollResult)
async def get_result(db: DB, user: CurrentUser, poll_id: int) -> PollResult:
    poll = await get_published_poll(db, poll_id)
    if poll_status(poll) != PollStatus.closed:
        raise AppError("RESULT_NOT_AVAILABLE")

    counts = await option_counts(db, poll.id)
    total = sum(c for _, _, c in counts)
    top = max((c for _, _, c in counts), default=0)
    return PollResult(
        poll_id=poll.id,
        title=poll.title,
        target_date=poll.target_date,
        closed_at=poll.closes_at,
        total_votes=total,
        results=[
            OptionResult(
                option_id=oid,
                menu_name=name,
                vote_count=count,
                percentage=pct(count, total),
                is_winner=top > 0 and count == top,  # ties: all top options win
            )
            for oid, name, count in counts
        ],
    )
