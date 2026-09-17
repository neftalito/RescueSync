from fastapi import APIRouter

from app.api.routes import auth, bonita, health

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["autenticación"])
api_router.include_router(
    bonita.router,
    prefix="/emergencias",
    tags=["callbacks de Bonita"],
)
