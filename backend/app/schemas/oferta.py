"""Esquemas HTTP para registrar una oferta básica de una ONG."""

from decimal import Decimal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.db.models.enums import EstadoOferta, GravedadEmergencia, TipoAporte


class LoteOfertaDisponibleResponse(BaseModel):
    """Snapshot de un lote publicado que admite ofertas."""

    lote_id: int
    tipo_necesidad: str
    descripcion: str | None
    cantidad_publicada: Decimal
    unidad_publicada: str


class ConvocatoriaOfertaDisponibleResponse(BaseModel):
    """Convocatoria abierta y sus lotes publicados disponibles para una ONG."""

    id: int
    numero: int
    emergencia_id: int
    gravedad: GravedadEmergencia
    zona: str
    lotes: list[LoteOfertaDisponibleResponse]


class OfertaItemRequest(BaseModel):
    """Aporte positivo sobre un lote publicado de la convocatoria."""

    lote_id: int = Field(gt=0)
    tipo: TipoAporte
    descripcion: str = Field(min_length=1, max_length=2000)
    cantidad_ofrecida: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    unidad: str = Field(min_length=1, max_length=40)

    @field_validator("descripcion", "unidad", mode="before")
    @classmethod
    def recortar_texto(cls, valor: object) -> object:
        return valor.strip() if isinstance(valor, str) else valor


class OfertaCreateRequest(BaseModel):
    """Oferta de la ONG autenticada sobre uno o más lotes de una convocatoria."""

    convocatoria_id: int = Field(gt=0)
    observaciones: str | None = Field(default=None, max_length=4000)
    items: list[OfertaItemRequest] = Field(min_length=1)

    @field_validator("observaciones", mode="before")
    @classmethod
    def recortar_observaciones(cls, valor: object) -> object:
        return valor.strip() if isinstance(valor, str) else valor

    @model_validator(mode="after")
    def rechazar_lotes_duplicados(self) -> "OfertaCreateRequest":
        ids = [item.lote_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("La oferta no puede repetir el mismo lote.")
        return self


class OfertaItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lote_id: int
    tipo: TipoAporte
    descripcion: str
    cantidad_ofrecida: Decimal
    unidad: str


class OfertaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    convocatoria_id: int
    emergencia_id: int
    ong_creadora_id: int
    creada_por_usuario_id: int
    estado: EstadoOferta
    version_actual: int
    observaciones: str | None
    presentada_en: AwareDatetime
    creada_en: AwareDatetime
    items: list[OfertaItemResponse]
