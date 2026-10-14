"""Esquemas HTTP para la publicación de convocatorias."""

from decimal import Decimal
from uuid import UUID

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
    tipo_necesidad: str
    descripcion: str | None
    cantidad_publicada: Decimal
    unidad_publicada: str
    capacidad_nacional_id: UUID | None = None
    codigo_capacidad_publicada: str | None = None
    riesgo_requerido_publicado: GravedadEmergencia | None = None


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


class ConvocatoriaAbiertaResponse(BaseModel):
    """Convocatoria abierta con el contexto de la emergencia para la ONG."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    emergencia_id: int
    numero: int
    estado: EstadoConvocatoria
    publicada_en: AwareDatetime
    cierra_en: AwareDatetime
    lotes: list[LotePublicadoResponse]
    emergencia: EmergenciaResumenResponse
    requiere_desglose_nacional: bool = False
