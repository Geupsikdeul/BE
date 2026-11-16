"""AI 보조 기능 (관리자 전용 — /admin 라우터의 require_admin을 상속).

DB에서 데이터를 모은 뒤, 동기 Anthropic 호출은 스레드풀에서 실행한다.
"""

import hashlib
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool

from app.ai.candidates import Candidate, rank_candidates
from app.ai.llm import AIError
from app.ai.menu_draft import CatalogMenu, MenuDraft, generate_menu_draft
from app.ai.recommendation import RecommendationResult, recommend_poll_menus
from app.ai.wish_analysis import Wish as AIWish
from app.ai.wish_analysis import WishAnalysis, analyze_wishes
from app.api.deps import DB
from app.core import clock
from app.core.errors import AppError
from app.models import MealCalendar, MealPoll, PollOption, Student, Wish, WishLike
from app.models.enums import MealType, Role

router = APIRouter(prefix="/ai", tags=["admin-ai"])

RECENT_DAYS = 14
CATALOG_LOOKBACK_DAYS = 90


def _raise(exc: AIError) -> None:
    raise AppError(exc.code, message=exc.message) from exc


async def _run(fn, *args):
    try:
        return await run_in_threadpool(fn, *args)
    except AIError as exc:
        _raise(exc)


def _split(menu: str | None) -> tuple[str, str]:
    parts = [p.strip() for p in (menu or "").replace("·", ",").split(",") if p.strip()]
    return (parts[0] if parts else ""), " · ".join(parts[1:])


async def _wishes(db: DB) -> list[AIWish]:
    likes = (
        select(func.count(WishLike.id))
        .where(WishLike.wish_id == Wish.id)
        .correlate(Wish)
        .scalar_subquery()
    )
    rows = await db.execute(select(Wish.id, Wish.menu_name, Wish.reason, likes))
    return [AIWish(id=i, menu_name=m, reason=r, likes=n or 0) for i, m, r, n in rows]


async def _analysis(db: DB) -> WishAnalysis:
    return await _run(analyze_wishes, await _wishes(db))


async def _recent_menus(db: DB) -> list[str]:
    today = clock.today_kst()
    cals = await db.scalars(
        select(MealCalendar).where(
            MealCalendar.service_date.between(
                today - timedelta(days=RECENT_DAYS), today + timedelta(days=RECENT_DAYS)
            )
        )
    )
    menus = []
    for cal in cals:
        for meal in MealType:
            if getattr(cal, f"{meal}_available"):
                main, _ = _split(getattr(cal, f"{meal}_menu"))
                if main:
                    menus.append(main)
    return menus


async def _active_poll_menus(db: DB) -> list[str]:
    rows = await db.scalars(
        select(PollOption.menu_name)
        .join(MealPoll, MealPoll.id == PollOption.poll_id)
        .where(MealPoll.closes_at > clock.now())
    )
    return list(rows)


class CandidatesResponse(BaseModel):
    analysis: WishAnalysis
    candidates: list[Candidate]


@router.post("/wish-analysis", response_model=WishAnalysis)
async def wish_analysis(db: DB) -> WishAnalysis:
    """희망 메뉴를 같은 음식끼리 묶고 요약."""
    return await _analysis(db)


@router.post("/poll-candidates", response_model=CandidatesResponse)
async def poll_candidates(db: DB) -> CandidatesResponse:
    """희망 메뉴 분석 → 공감·제안 수로 투표 후보 선정 (최근 식단과 겹치면 감점)."""
    analysis = await _analysis(db)
    candidates = rank_candidates(analysis.groups, await _recent_menus(db))
    return CandidatesResponse(analysis=analysis, candidates=candidates)


@router.post("/poll-recommendations", response_model=RecommendationResult)
async def poll_recommendations(db: DB) -> RecommendationResult:
    """희망 메뉴 + 학생 알레르기 집계(5명 이상 성분만)로 투표에 추가할 새 메뉴 추천."""
    analysis = await _analysis(db)
    students = [
        list(a)
        for a in await db.scalars(
            select(Student.allergies).where(
                Student.role == Role.student,
                Student.is_active.is_(True),
                Student.allergies.is_not(None),
            )
        )
    ]
    existing = await _active_poll_menus(db)
    return await _run(recommend_poll_menus, analysis.groups, students, existing)


# ---- menu draft ----


def _menu_id(meal: str, menu: str) -> str:
    return meal[0].upper() + hashlib.sha1(f"{meal}:{menu}".encode()).hexdigest()[:6]


async def menu_catalog(db: DB) -> list[CatalogMenu]:
    """지난 급식 일정의 메뉴(알레르기 정보 포함) + 진행 중 투표 선택지(알레르기 미확인)."""
    since = clock.today_kst() - timedelta(days=CATALOG_LOOKBACK_DAYS)
    cals = await db.scalars(
        select(MealCalendar)
        .where(MealCalendar.service_date >= since)
        .order_by(MealCalendar.service_date)
    )
    catalog: dict[str, CatalogMenu] = {}
    for cal in cals:
        for meal in MealType:
            menu = getattr(cal, f"{meal}_menu")
            if not getattr(cal, f"{meal}_available") or not menu:
                continue
            main, details = _split(menu)
            mid = _menu_id(meal.value, menu)
            catalog[mid] = CatalogMenu(
                id=mid,
                meal_type=meal.value,
                main=main,
                details=details,
                allergens=getattr(cal, f"{meal}_allergens"),
            )
    rows = await db.execute(
        select(PollOption.menu_name, PollOption.description)
        .join(MealPoll, MealPoll.id == PollOption.poll_id)
        .where(MealPoll.closes_at > clock.now() - timedelta(days=30))
    )
    for name, desc in rows:
        mid = _menu_id("dinner", name)
        catalog.setdefault(
            mid,
            CatalogMenu(id=mid, meal_type="dinner", main=name, details=desc or "", allergens=None),
        )
    return list(catalog.values())


class CatalogResponse(BaseModel):
    items: list[CatalogMenu]


class MenuDraftRequest(BaseModel):
    start_date: date
    days: int = Field(default=14, ge=1, le=14)
    must_include: list[str] = Field(default_factory=list, max_length=10)


@router.get("/menu-catalog", response_model=CatalogResponse)
async def get_menu_catalog(db: DB) -> CatalogResponse:
    """식단 초안의 must_include에 쓸 메뉴 ID 목록."""
    return CatalogResponse(items=await menu_catalog(db))


@router.post("/menu-draft", response_model=MenuDraft)
async def menu_draft(db: DB, payload: Annotated[MenuDraftRequest, Body()]) -> MenuDraft:
    """날짜·끼니별 식단 초안 + 규칙 검사(반복, 필수 메뉴, 알레르기 미등록). 저장하지 않음."""
    catalog = await menu_catalog(db)
    known = {m.id for m in catalog}
    unknown = [m for m in payload.must_include if m not in known]
    if unknown:
        raise AppError("UNKNOWN_MENU", {"menu_ids": unknown})
    if not catalog:
        raise AppError(
            "UNKNOWN_MENU",
            message="식단 초안에 쓸 메뉴가 없습니다. 급식 일정을 먼저 등록해 주세요.",
        )
    return await _run(
        generate_menu_draft, payload.start_date, payload.days, catalog, payload.must_include
    )
