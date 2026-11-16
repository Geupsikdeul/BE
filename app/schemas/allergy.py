from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field

from app.models.enums import ALLERGENS

Allergen = Literal[ALLERGENS]  # type: ignore[valid-type]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


AllergenList = Annotated[list[Allergen], Field(max_length=len(ALLERGENS)), AfterValidator(_dedupe)]


class AllergyUpdate(BaseModel):
    allergies: AllergenList


class AllergyRead(BaseModel):
    allergies: list[str]
    registered: bool  # False = 아직 등록 안 함 ([]로 등록한 '없음'과 구분)
