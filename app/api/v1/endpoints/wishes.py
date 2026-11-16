from fastapi import APIRouter
from sqlalchemy import and_, delete, exists, func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, CurrentUser
from app.core import clock
from app.core.errors import AppError
from app.models import Student, Wish, WishLike
from app.schemas.wish import LikeResult, WishCreate, WishList, WishRead

router = APIRouter(prefix="/wishes", tags=["wishes"])


def _author(grade: int | None) -> str:
    return f"{grade}학년 익명" if grade else "익명"


def _like_count():
    return (
        select(func.count(WishLike.id))
        .where(WishLike.wish_id == Wish.id)
        .correlate(Wish)
        .scalar_subquery()
    )


@router.get("", response_model=WishList)
async def list_wishes(db: DB, user: CurrentUser) -> WishList:
    likes = _like_count().label("likes")
    liked = exists().where(and_(WishLike.wish_id == Wish.id, WishLike.student_id == user.id))
    rows = await db.execute(
        select(Wish, Student.grade, likes, liked.label("liked"))
        .join(Student, Student.id == Wish.student_id)
        .order_by(likes.desc(), Wish.id.desc())
    )
    items = [
        WishRead(
            id=w.id,
            menu_name=w.menu_name,
            reason=w.reason,
            emoji=w.emoji,
            author=_author(grade),
            likes=n or 0,
            liked=bool(is_liked),
            is_mine=w.student_id == user.id,
            created_at=w.created_at,
        )
        for w, grade, n, is_liked in rows
    ]
    return WishList(items=items, total=len(items))


@router.post("", response_model=WishRead, status_code=201)
async def create_wish(db: DB, user: CurrentUser, payload: WishCreate) -> WishRead:
    wish = Wish(student_id=user.id, created_at=clock.now(), **payload.model_dump())
    db.add(wish)
    await db.commit()
    return WishRead(
        id=wish.id,
        menu_name=wish.menu_name,
        reason=wish.reason,
        emoji=wish.emoji,
        author=_author(user.grade),
        likes=0,
        liked=False,
        is_mine=True,
        created_at=wish.created_at,
    )


@router.post("/{wish_id}/like", response_model=LikeResult)
async def toggle_like(db: DB, user: CurrentUser, wish_id: int) -> LikeResult:
    """공감 토글. 이미 공감했으면 취소, 아니면 공감."""
    if await db.get(Wish, wish_id) is None:
        raise AppError("WISH_NOT_FOUND")
    removed = await db.execute(
        delete(WishLike).where(WishLike.wish_id == wish_id, WishLike.student_id == user.id)
    )
    liked = removed.rowcount == 0
    if liked:
        db.add(WishLike(wish_id=wish_id, student_id=user.id, created_at=clock.now()))
    try:
        await db.commit()
    except IntegrityError:  # 동시에 두 번 눌린 경우 — 이미 공감된 상태
        await db.rollback()
        liked = True
    count = await db.scalar(select(func.count(WishLike.id)).where(WishLike.wish_id == wish_id))
    return LikeResult(id=wish_id, likes=count or 0, liked=liked)


@router.delete("/{wish_id}", status_code=204)
async def delete_my_wish(db: DB, user: CurrentUser, wish_id: int) -> None:
    wish = await db.get(Wish, wish_id)
    if wish is None:
        raise AppError("WISH_NOT_FOUND")
    if wish.student_id != user.id:
        raise AppError("FORBIDDEN")
    await db.delete(wish)
    await db.commit()
