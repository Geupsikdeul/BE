from fastapi import APIRouter

from app.api.deps import DB
from app.core.errors import AppError
from app.models import Wish

router = APIRouter(prefix="/wishes")


@router.delete("/{wish_id}", status_code=204)
async def delete_wish(db: DB, wish_id: int) -> None:
    """부적절한 희망 메뉴 삭제 (관리자)."""
    wish = await db.get(Wish, wish_id)
    if wish is None:
        raise AppError("WISH_NOT_FOUND")
    await db.delete(wish)
    await db.commit()
