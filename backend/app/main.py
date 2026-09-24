from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.integrations.bonita.cliente import ClienteBonita, ConfiguracionBonita
from app.services.bootstrap import asegurar_admin_inicial

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Comparte un único cliente de Bonita y cierra su pool al apagar la API."""

    if settings.app_env.casefold() in {"development", "production"}:
        with SessionLocal.begin() as session:
            asegurar_admin_inicial(session, settings)

    with ClienteBonita(ConfiguracionBonita.desde_settings(settings)) as cliente:
        app.state.cliente_bonita = cliente
        yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="API local para la coordinación de emergencias de RescueSync.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "docs": "/docs",
        "health": f"{settings.api_v1_prefix}/health",
    }
