from fastapi import APIRouter

from app.api.routes import (
    auth,
    bonita,
    convocatorias,
    emergencias,
    health,
    lotes,
    ofertas,
    usuarios,
)

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["autenticación"])
api_router.include_router(usuarios.router, prefix="/usuarios", tags=["usuarios"])
api_router.include_router(
    usuarios.organizaciones_router,
    prefix="/organizaciones",
    tags=["organizaciones"],
)
api_router.include_router(
    emergencias.router,
    prefix="/emergencias",
    tags=["emergencias"],
)
api_router.include_router(
    lotes.router,
    prefix="/emergencias",
    tags=["lotes"],
)
api_router.include_router(
    convocatorias.router,
    prefix="/emergencias",
    tags=["convocatorias"],
)
api_router.include_router(
    bonita.router,
    prefix="/emergencias",
    tags=["callbacks de Bonita"],
)
api_router.include_router(
    ofertas.router,
    prefix="/ofertas",
    tags=["ofertas"],
)
