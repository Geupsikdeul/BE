from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Literal

import anthropic
from pydantic import BaseModel

from .candidates import same_food
from .llm import parse

MealType = Literal["breakfast", "dinner"]
MIN_REPEAT_GAP_DAYS = 3

SYSTEM = f"""당신은 학교 영양사를 돕는 식단 초안 작성자입니다.
주어진 메뉴 목록에서 골라 날짜와 끼니별 식단을 채웁니다.

규칙:
- <slots>의 모든 날짜와 끼니를 정확히 한 번씩 채웁니다.
- menu_id는 <catalog>에서 meal_type이 같은 항목만 씁니다.
- 같은 끼니에 같은 음식을 {MIN_REPEAT_GAP_DAYS}일 안에 반복하지 않습니다. 이름에 같은 음식명이 들어가면 ID가 달라도 같은 음식입니다.
- <must_include>의 메뉴는 반드시 한 번 이상 넣습니다.
- 며칠 동안 비슷한 조리법이나 재료가 이어지지 않게 조합합니다.
- notes에는 구성 의도를 한두 문장으로 씁니다. 메뉴는 ID가 아니라 이름으로 부릅니다.
- notes에 <catalog>에 없는 조리법이나 음식 분류를 쓰지 않습니다.
- 영양이나 알레르기 안전을 보장하는 표현은 쓰지 않습니다."""


class CatalogMenu(BaseModel):
    id: str
    meal_type: MealType
    main: str
    details: str
    allergens: list[str] | None


class AIMeal(BaseModel):
    service_date: str
    meal_type: MealType
    menu_id: str


class AIDraft(BaseModel):
    meals: list[AIMeal]
    notes: str


class DraftMeal(BaseModel):
    service_date: str
    meal_type: MealType
    menu_id: str
    main: str
    details: str
    allergens: list[str]
    allergens_confirmed: bool


class MenuDraft(BaseModel):
    status: Literal["draft"] = "draft"
    meals: list[DraftMeal]
    notes: str
    violations: list[str]


def service_slots(start: date, days: int) -> list[tuple[str, MealType]]:
    slots: list[tuple[str, MealType]] = []
    for offset in range(days):
        current = start + timedelta(days=offset)
        if current.weekday() < 5:
            slots.append((current.isoformat(), "breakfast"))
            slots.append((current.isoformat(), "dinner"))
    return slots


def _clean_notes(notes: str, catalog: list[CatalogMenu]) -> str:
    """AI가 설명에 내부 메뉴 ID를 쓰면 메뉴 이름으로 바꾼다."""
    for menu in catalog:
        notes = re.sub(rf"(?<![A-Za-z0-9]){re.escape(menu.id)}(?![A-Za-z0-9])", menu.main, notes)
    return notes


def validate_draft(
    result: AIDraft,
    slots: list[tuple[str, MealType]],
    catalog: list[CatalogMenu],
    must_include: list[str],
) -> MenuDraft:
    """AI 결과를 규칙으로 검사한다. 메뉴와 알레르기 정보는 항상 catalog 값을 쓴다."""
    menus = {menu.id: menu for menu in catalog}
    slot_set = set(slots)
    chosen: dict[tuple[str, MealType], DraftMeal] = {}
    violations: list[str] = []

    for meal in result.meals:
        slot = (meal.service_date, meal.meal_type)
        menu = menus.get(meal.menu_id)
        if slot not in slot_set:
            violations.append(
                f"{meal.service_date} {meal.meal_type}: 운영 대상이 아닌 끼니라 제외했습니다."
            )
        elif slot in chosen:
            violations.append(
                f"{meal.service_date} {meal.meal_type}: 중복 배정이라 첫 번째 메뉴만 남겼습니다."
            )
        elif menu is None or menu.meal_type != meal.meal_type:
            violations.append(
                f"{meal.service_date} {meal.meal_type}: 목록에 없는 메뉴 {meal.menu_id}를 제외했습니다."
            )
        else:
            chosen[slot] = DraftMeal(
                service_date=meal.service_date,
                meal_type=meal.meal_type,
                menu_id=menu.id,
                main=menu.main,
                details=menu.details,
                allergens=menu.allergens or [],
                allergens_confirmed=menu.allergens is not None,
            )

    meals = [chosen[slot] for slot in slots if slot in chosen]
    for slot in slots:
        if slot not in chosen:
            violations.append(f"{slot[0]} {slot[1]}: 메뉴가 비어 있습니다.")

    for index, meal in enumerate(meals):
        current = date.fromisoformat(meal.service_date)
        for earlier in meals[:index]:
            gap = (current - date.fromisoformat(earlier.service_date)).days
            if (
                earlier.meal_type == meal.meal_type
                and gap < MIN_REPEAT_GAP_DAYS
                and same_food(earlier.main, meal.main)
            ):
                violations.append(
                    f"{meal.service_date} {meal.main}: {MIN_REPEAT_GAP_DAYS}일 안에 반복됩니다."
                )
                break

    used = {meal.menu_id for meal in meals}
    for menu_id in must_include:
        if menu_id not in used:
            name = menus[menu_id].main if menu_id in menus else menu_id
            violations.append(f"필수 메뉴 {name}가 초안에 없습니다.")
    for meal in meals:
        if not meal.allergens_confirmed:
            violations.append(
                f"{meal.service_date} {meal.main}: 알레르기 정보가 등록되지 않았습니다."
            )

    return MenuDraft(meals=meals, notes=_clean_notes(result.notes, catalog), violations=violations)


def generate_menu_draft(
    start: date,
    days: int,
    catalog: list[CatalogMenu],
    must_include: list[str] | None = None,
    client: anthropic.Anthropic | None = None,
) -> MenuDraft:
    required = must_include or []
    slots = service_slots(start, days)
    if not slots:
        return MenuDraft(meals=[], notes="", violations=[])

    offered = [menu for menu in catalog if menu.allergens is not None or menu.id in required]
    menu_payload = [menu.model_dump(exclude={"allergens"}) for menu in offered]
    slot_payload = [{"service_date": day, "meal_type": meal} for day, meal in slots]
    prompt = (
        f"<catalog>\n{json.dumps(menu_payload, ensure_ascii=False)}\n</catalog>\n"
        f"<slots>\n{json.dumps(slot_payload, ensure_ascii=False)}\n</slots>\n"
        f"<must_include>\n{json.dumps(required, ensure_ascii=False)}\n</must_include>"
    )
    result = parse(SYSTEM, prompt, AIDraft, client=client)
    return validate_draft(result, slots, offered, required)
