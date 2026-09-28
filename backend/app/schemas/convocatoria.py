"""Esquemas HTTP para la publicación de convocatorias."""

from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, ConfigDict

from app.db.models.enums import (
    EstadoConvocatoria,
    EstadoTareaBonita,
    GravedadEmergencia,
)


class LotePublicadoResponse(BaseModel):
    """Snapshot de un lote incluido en la convocatoria publicada."""

    model_config = ConfigDict(from_attributes=True)

    lote_id: int
    cantidad_publicada: Decimal
    unidad_publicada: str


class ConvocatoriaResponse(BaseModel):
    """Convocatoria recién publicada con el detalle de sus lotes."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    emergencia_id: int
    numero: int
    estado: EstadoConvocatoria
    publicada_en: AwareDatetime
    cierra_en: AwareDatetime
    lotes: list[LotePublicadoResponse]
    bonita_generar_lotes_estado: EstadoTareaBonita
    bonita_generar_lotes_ultimo_error: str | None
    bonita_generar_lotes_ultimo_intento_en: AwareDatetime | None


class EmergenciaResumenResponse(BaseModel):
    """Contexto mínimo de la emergencia para que la ONG identifique la convocatoria."""

    model_config = ConfigDict(from_attributes=True)

    zona: str
    gravedad: GravedadEmergencia
    descripcion: str


class ConvocatoriaAbiertaResponse(ConvocatoriaResponse):
    """Convocatoria abierta con el contexto de la emergencia para la ONG."""

    emergencia: EmergenciaResumenResponse
