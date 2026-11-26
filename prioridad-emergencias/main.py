"""Servicio de cálculo de prioridad para emergencias de RescueSync."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="RescueSync · Prioridad de emergencias", version="1.0.0")

BASE_POR_GRAVEDAD = {"BAJA": 1, "MEDIA": 3, "ALTA": 5, "CRITICA": 8}
AJUSTE_POR_ZONA = {"NORTE": 0, "CENTRO": 1, "SUR": 2}


class SolicitudPrioridad(BaseModel):
    """Datos de la emergencia que determinan la prioridad."""

    gravedad: Literal["BAJA", "MEDIA", "ALTA", "CRITICA"]
    zona: Literal["NORTE", "CENTRO", "SUR"]


class PrioridadResponse(BaseModel):
    prioridad: int = Field(ge=1, le=10)


@app.post("/prioridades", summary="Calcular la prioridad de una emergencia")
async def calcular_prioridad(datos: SolicitudPrioridad) -> PrioridadResponse:
    prioridad = BASE_POR_GRAVEDAD[datos.gravedad] + AJUSTE_POR_ZONA[datos.zona]
    return PrioridadResponse(prioridad=prioridad)


@app.get("/health", summary="Comprobar la disponibilidad del servicio")
async def health() -> dict[str, str]:
    return {"estado": "ok"}
