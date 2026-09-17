"""Modelos HTTP de los callbacks que el proceso RescueSync envía a FastAPI."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, PlainSerializer
from pydantic.alias_generators import to_camel

from app.db.models import EstadoConvocatoria, EstadoOferta, TipoAporte

Cantidad = Annotated[
    Decimal, PlainSerializer(float, return_type=float, when_used="json")
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


class ItemOfertaConsolidado(_ModeloCallback):
    """Aporte de una oferta para un lote."""

    lote_id: int
    tipo: TipoAporte
    descripcion: str
    cantidad_ofrecida: Cantidad
    unidad: str


class OfertaConsolidada(_ModeloCallback):
    """Versión vigente y presentada de una oferta."""

    oferta_id: int
    ong_id: int
    estado: EstadoOferta
    version: int
    presentada_en: datetime
    items: list[ItemOfertaConsolidado]


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
