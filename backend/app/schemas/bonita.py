"""Modelos HTTP de los callbacks que el proceso RescueSync envía a FastAPI."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, PlainSerializer
from pydantic.alias_generators import to_camel

from app.db.models import (
    EstadoConvocatoria,
    EstadoOferta,
    GravedadEmergencia,
    TipoAporte,
    TipoParticipacion,
)

Cantidad = Annotated[
    Decimal, PlainSerializer(float, return_type=float, when_used="json")
]


def cantidad_exacta(valor: Decimal) -> str:
    return format(valor, ".3f")


CantidadExacta = Annotated[
    Decimal, PlainSerializer(cantidad_exacta, return_type=str, when_used="json")
]


class _ModeloCallback(BaseModel):
    """Usa camelCase, que es la convención de las variables del proceso."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        serialize_by_alias=True,
    )


class NotificacionAperturaRequest(_ModeloCallback):
    """Cuerpo enviado por `Enviar notificacion a ONGs de convocatoria`."""

    id_emergencia: int = Field(gt=0)
    intento_convocatoria: int = Field(gt=0)
    fecha_cierre_ofertas: AwareDatetime


class CierreConvocatoriaRequest(_ModeloCallback):
    """Cuerpo enviado por `Cerrar convocatoria local` al vencer el timer."""

    id_emergencia: int = Field(gt=0)
    intento_convocatoria: int = Field(gt=0)


class ConvocatoriaBonitaResponse(_ModeloCallback):
    """Estado local de la convocatoria después de procesar el callback."""

    id_emergencia: int
    convocatoria_id: int
    numero: int
    estado: EstadoConvocatoria
    cierra_en: datetime
    cerrada_en: datetime | None


class LoteConsolidado(_ModeloCallback):
    """Cobertura de un lote publicado en la convocatoria."""

    lote_id: int
    tipo_necesidad: str
    cantidad_publicada: Cantidad
    unidad: str
    cantidad_ofrecida: Cantidad
    cubierto: bool
    capacidad_nacional_id: UUID | None = None
    codigo_capacidad: str | None = None
    riesgo_requerido: GravedadEmergencia | None = None
    cantidad_publicada_exacta: CantidadExacta
    cantidad_ofrecida_exacta: CantidadExacta


class CodigoMotivoIntegracion(StrEnum):
    ONG_NACIONAL_NO_ASOCIADA = "ONG_NACIONAL_NO_ASOCIADA"
    CAPACIDAD_NACIONAL_NO_ASOCIADA = "CAPACIDAD_NACIONAL_NO_ASOCIADA"
    DESGLOSE_NACIONAL_AUSENTE = "DESGLOSE_NACIONAL_AUSENTE"
    SISTEMA_ORIGEN_NO_ASOCIADO = "SISTEMA_ORIGEN_NO_ASOCIADO"
    RIESGO_PUBLICADO_AUSENTE = "RIESGO_PUBLICADO_AUSENTE"
    PARTICIPANTES_NO_VERSIONADOS = "PARTICIPANTES_NO_VERSIONADOS"


class MotivoIntegracion(_ModeloCallback):
    codigo: CodigoMotivoIntegracion
    mensaje: str
    oferta_id: int | None = None
    version: int | None = None
    ong_id: int | None = None
    lote_id: int | None = None
    item_id: int | None = None


class ParticipanteConsolidado(_ModeloCallback):
    ong_id: int
    ong_nacional_id: UUID | None
    rol: TipoParticipacion


class AporteConsolidado(_ModeloCallback):
    aporte_id: int
    ong_id: int
    ong_nacional_id: UUID | None
    recurso_nacional_id: UUID
    capacidad_nacional_id: UUID
    cantidad: CantidadExacta
    unidad: str


class ItemOfertaConsolidado(_ModeloCallback):
    """Aporte de una oferta para un lote."""

    lote_id: int
    tipo: TipoAporte
    descripcion: str
    cantidad_ofrecida: Cantidad
    unidad: str
    item_id: int
    cantidad_ofrecida_exacta: CantidadExacta
    aportes: list[AporteConsolidado] = Field(default_factory=list)


class OfertaConsolidada(_ModeloCallback):
    """Versión vigente y presentada de una oferta."""

    oferta_id: int
    ong_id: int
    estado: EstadoOferta
    version: int
    presentada_en: datetime
    items: list[ItemOfertaConsolidado]
    ong_nacional_id: UUID | None = None
    participantes: list[ParticipanteConsolidado] = Field(default_factory=list)
    referencias_nacionales_completas: bool
    motivos_integracion: list[MotivoIntegracion] = Field(default_factory=list)


class OfertasConsolidadasResponse(_ModeloCallback):
    """Consolidado que Bonita guarda en `ofertasConsolidadasJson`.

    El proceso decide la compuerta `Lotes cubiertos?` con `lotesCubiertos`.
    """

    id_emergencia: int
    convocatoria_id: int
    numero: int
    lotes_cubiertos: bool
    lotes: list[LoteConsolidado]
    ofertas: list[OfertaConsolidada]
    contrato_version: int = 2
    sistema_origen: str | None = None
    case_id: str
    gravedad: GravedadEmergencia | None
    cerrada_en: AwareDatetime | None
    referencias_nacionales_completas: bool
    motivos_integracion: list[MotivoIntegracion] = Field(default_factory=list)
