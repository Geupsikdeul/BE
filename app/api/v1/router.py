from fastapi import APIRouter

from app.api.v1.endpoints import admin, auth, health, meals, polls, wishes

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(polls.router)
api_router.include_router(meals.router)
api_router.include_router(wishes.router)
api_router.include_router(admin.router)
