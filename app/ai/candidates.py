from __future__ import annotations

from pydantic import BaseModel

from .wish_analysis import WishGroup

LIKES_WEIGHT = 0.7
WISH_COUNT_WEIGHT = 0.3
RECENT_MENU_PENALTY = 0.5
DEFAULT_LIMIT = 4


class Candidate(BaseModel):
    name: str
    category: str
    score: float
    total_likes: int
    wish_count: int
    recently_served: bool
    reason: str


def normalize_name(text: str) -> str:
    return "".join(text.split()).lower()


def same_food(left: str, right: str) -> bool:
    first, second = normalize_name(left), normalize_name(right)
    return bool(first and second) and (first in second or second in first)


def _is_recent(group: WishGroup, recent_menus: list[str]) -> bool:
    return any(
        same_food(name, menu) for name in [group.name, *group.menu_names] for menu in recent_menus
    )


def _score(group: WishGroup, max_likes: int, max_wishes: int, recent: bool) -> float:
    likes = group.total_likes / max_likes if max_likes else 0.0
    wishes = group.wish_count / max_wishes if max_wishes else 0.0
    score = LIKES_WEIGHT * likes + WISH_COUNT_WEIGHT * wishes
    return round(score * (1 - RECENT_MENU_PENALTY) if recent else score, 3)


def rank_candidates(
    groups: list[WishGroup],
    recent_menus: list[str],
    limit: int = DEFAULT_LIMIT,
) -> list[Candidate]:
    """공감 수와 제안 수로 점수를 매기고, 후보가 한 종류로 쏠리지 않게 고른다."""
    if not groups:
        return []

    max_likes = max(group.total_likes for group in groups)
    max_wishes = max(group.wish_count for group in groups)
    candidates = []
    for group in groups:
        recent = _is_recent(group, recent_menus)
        reason = f"공감 {group.total_likes}개, 제안 {group.wish_count}건"
        candidates.append(
            Candidate(
                name=group.name,
                category=group.category,
                score=_score(group, max_likes, max_wishes, recent),
                total_likes=group.total_likes,
                wish_count=group.wish_count,
                recently_served=recent,
                reason=f"{reason}, 최근 식단과 겹침" if recent else reason,
            )
        )
    candidates.sort(key=lambda item: (-item.score, item.name))

    first_of_category: list[Candidate] = []
    rest: list[Candidate] = []
    categories: set[str] = set()
    for candidate in candidates:
        if candidate.category in categories:
            rest.append(candidate)
        else:
            categories.add(candidate.category)
            first_of_category.append(candidate)

    selected = (first_of_category + rest)[:limit]
    return sorted(selected, key=lambda item: (-item.score, item.name))
