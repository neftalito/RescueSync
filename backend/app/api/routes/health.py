from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import SessionLocal

router = APIRouter()


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
