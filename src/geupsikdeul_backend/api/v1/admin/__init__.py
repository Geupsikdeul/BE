from fastapi import APIRouter, Depends

from geupsikdeul_backend.api.deps import require_admin
from geupsikdeul_backend.api.v1.admin import meals, polls, students

# require_admin applied once at router level — every /admin/* route inherits it.
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])
router.include_router(students.router)
router.include_router(polls.router)
router.include_router(meals.router)
