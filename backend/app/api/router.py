from fastapi import APIRouter

from app.api.routes import (
    auth,
    bonita,
    catalogo,
    convocatorias,
    ejecucion,
    emergencias,
    health,
    inventario,
    lotes,
    metricas,
    notificaciones,
    ofertas,
    organizaciones,
    usuarios,
)

api_router = APIRouter()
api_router.include_router(metricas.router, prefix="/metricas", tags=["métricas"])
api_router.include_router(
    catalogo.router, prefix="/catalogo-nacional", tags=["catálogo nacional"]
)
api_router.include_router(
    inventario.router, prefix="/mi-ong", tags=["inventario nacional"]
)
api_router.include_router(
    inventario.router_admin, prefix="/organizaciones", tags=["organizaciones"]
)
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["autenticación"])
api_router.include_router(usuarios.router, prefix="/usuarios", tags=["usuarios"])
api_router.include_router(
    organizaciones.router,
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
    convocatorias.router_publico,
    prefix="/convocatorias",
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
api_router.include_router(
    notificaciones.router,
    prefix="/notificaciones",
    tags=["notificaciones"],
)

api_router.include_router(
    ejecucion.tecnico, prefix="/emergencias", tags=["integración nacional Bonita"]
)
api_router.include_router(
    ejecucion.router, prefix="/emergencias", tags=["ejecución de emergencias"]
)
