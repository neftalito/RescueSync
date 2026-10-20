"""Detalles de consulta vinculados al evento de una notificación propia."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.db.models.enums import EstadoEmergencia, EstadoOferta
from app.schemas.convocatoria import (
    ConvocatoriaAbiertaResponse,
    EmergenciaResumenResponse,
)
from app.schemas.oferta import AporteResponse, OfertaItemResponse, ParticipanteResponse


class EmergenciaNotificadaResponse(EmergenciaResumenResponse):
    id: int
    estado: EstadoEmergencia


class ItemNotificadoResponse(OfertaItemResponse):
    necesidad: str
    aportes: list[AporteResponse] = Field(default_factory=list)


class OfertaNotificadaResponse(BaseModel):
    id: int
    estado: EstadoOferta
    version: int
    presentada_en: datetime | None
    observaciones: str | None
    participantes: list[ParticipanteResponse]
    items: list[ItemNotificadoResponse]


class DetalleOfertaRecibidaResponse(BaseModel):
    clase: Literal["OFERTA_RECIBIDA"] = "OFERTA_RECIBIDA"
    emergencia: EmergenciaNotificadaResponse
    oferta: OfertaNotificadaResponse
    convocatoria_numero: int


class DetalleConvocatoriaResponse(BaseModel):
    clase: Literal["CONVOCATORIA"] = "CONVOCATORIA"
    emergencia: EmergenciaNotificadaResponse
    convocatoria: ConvocatoriaAbiertaResponse
    mi_oferta: OfertaNotificadaResponse | None


class DetalleTareaFallidaResponse(BaseModel):
    clase: Literal["TAREA_BONITA_FALLIDA"] = "TAREA_BONITA_FALLIDA"
    emergencia: EmergenciaNotificadaResponse
    tarea_id: int
    nombre: str
    estado_observado: Literal["failed"] = "failed"
    observada_en: datetime


DetalleNotificacionResponse = Annotated[
    DetalleOfertaRecibidaResponse
    | DetalleConvocatoriaResponse
    | DetalleTareaFallidaResponse,
    Field(discriminator="clase"),
]
