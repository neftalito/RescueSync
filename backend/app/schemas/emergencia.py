"""Esquemas HTTP para el registro municipal de emergencias."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.db.models.enums import (
    EstadoEmergencia,
    EstadoSincronizacionBonita,
    GravedadEmergencia,
)

ZonaPrioridad = Literal["NORTE", "CENTRO", "SUR"]


class SolicitudPrioridadEmergencia(BaseModel):
    """Identifica la gravedad y la zona que se envían al priorizador."""

    gravedad: GravedadEmergencia
    zona: ZonaPrioridad


class PrioridadCalculada(BaseModel):
    """Valida que el priorizador devuelva un entero dentro de su escala."""

    prioridad: int = Field(strict=True, ge=1, le=10)


class PrioridadEmergenciaResponse(PrioridadCalculada):
    comprobante: str


class EmergenciaCreate(BaseModel):
    """Datos obligatorios que envía el municipio para registrar una emergencia."""

    gravedad: GravedadEmergencia
    zona: str = Field(min_length=1, max_length=255)
    descripcion: str = Field(min_length=1, max_length=2000)

    @field_validator("zona", "descripcion", mode="before")
    @classmethod
    def recortar_texto(cls, valor: object) -> object:
        """Elimina espacios accidentales para rechazar textos solo con blancos."""

        return valor.strip() if isinstance(valor, str) else valor


class EmergenciaConPrioridadCreate(EmergenciaCreate):
    """Exige una consulta previa para los datos del alta municipal."""

    zona: ZonaPrioridad
    comprobante_prioridad: str | None = Field(default=None, max_length=2048)


class EmergenciaResponse(BaseModel):
    """Emergencia persistida con su estado inicial y vínculo municipal."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    municipio_id: int
    centro_coordinador_id: int | None
    creada_por_usuario_id: int
    gravedad: GravedadEmergencia
    zona: str
    prioridad: int | None
    descripcion: str
    estado: EstadoEmergencia
    bonita_sync: EstadoSincronizacionBonita
    bonita_process_instance_id: int | None
    bonita_ultimo_error: str | None
    bonita_ultimo_intento_en: AwareDatetime | None
    creada_en: AwareDatetime
    actualizada_en: AwareDatetime


class EmergenciaEnBandejaResponse(EmergenciaResponse):
    """Agrega la existencia de lotes para clasificar la bandeja del coordinador."""

    tiene_lotes: bool
