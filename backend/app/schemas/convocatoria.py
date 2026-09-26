"""Esquemas HTTP para la publicación de convocatorias."""

from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, ConfigDict

from app.db.models.enums import EstadoConvocatoria, GravedadEmergencia


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


class ConvocatoriaResumenResponse(BaseModel):
    """Convocatoria del centro coordinador en el listado de consulta."""

    id: int
    emergencia_id: int
    numero: int
    estado: EstadoConvocatoria
    publicada_en: AwareDatetime
    cierra_en: AwareDatetime
    cantidad_lotes: int
    gravedad: GravedadEmergencia
    zona: str


class ConvocatoriasListResponse(BaseModel):
    """Listado de convocatorias del centro coordinador autenticado."""

    items: list[ConvocatoriaResumenResponse]
