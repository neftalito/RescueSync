import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import ClienteBonitaDep
from app.db.session import SessionLocal
from app.integrations.bonita.cliente import ErrorBonita
from app.schemas import ErrorResponse

router = APIRouter()
LOGGER = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str


@router.get("", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness: indica que el proceso HTTP está respondiendo."""
    return HealthResponse(service="backend")


@router.get("/database", response_model=HealthResponse)
def database_health() -> HealthResponse:
    """Readiness: comprueba una conexión real con PostgreSQL."""
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL no está disponible",
        ) from exc

    return HealthResponse(service="database")


@router.get(
    "/bonita",
    response_model=HealthResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse}},
    summary="Comprobar Bonita",
)
def bonita_health(cliente: ClienteBonitaDep) -> HealthResponse:
    """Readiness: autentica en Bonita y exige el proceso configurado habilitado."""
    try:
        cliente.obtener_proceso_habilitado()
    except ErrorBonita as exc:
        LOGGER.warning("Bonita no está lista: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bonita no está disponible o el proceso no está habilitado",
        ) from exc

    return HealthResponse(service="bonita")
