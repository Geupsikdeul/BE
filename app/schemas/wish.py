from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class WishCreate(BaseModel):
    menu_name: str = Field(min_length=1, max_length=40)
    reason: str = Field(min_length=2, max_length=200)
    emoji: str = Field(default="🍽️", min_length=1, max_length=16)

    @field_validator("menu_name", "reason")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("공백만 입력할 수 없습니다.")
        return v


class WishRead(BaseModel):
    id: int
    menu_name: str
    reason: str
    emoji: str
    author: str  # "N학년 익명" — 작성자 신원은 노출하지 않음
    likes: int
    liked: bool
    is_mine: bool
    created_at: datetime


class WishList(BaseModel):
    items: list[WishRead]
    total: int


class LikeResult(BaseModel):
    id: int
    likes: int
    liked: bool
