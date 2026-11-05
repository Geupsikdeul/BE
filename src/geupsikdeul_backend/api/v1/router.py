from fastapi import APIRouter

from geupsikdeul_backend.api.v1 import admin, auth, health, meals, polls

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(polls.router)
api_router.include_router(meals.router)
api_router.include_router(admin.router)
