"""Esquemas HTTP para registrar una oferta básica de una ONG."""

from decimal import Decimal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.db.models.enums import EstadoOferta, TipoAporte, TipoParticipacion
from app.schemas.convocatoria import EmergenciaResumenResponse


class AporteRequest(BaseModel):
    """La ONG dueña se obtiene de la sesión; el navegador no puede elegirla."""

    model_config = ConfigDict(extra="forbid")
    recurso_nacional_id: UUID
    cantidad: Decimal = Field(
        gt=0, max_digits=14, decimal_places=3, allow_inf_nan=False
    )


class OfertaItemRequest(BaseModel):
    """Aporte positivo sobre un lote publicado de la convocatoria."""

    lote_id: int = Field(gt=0)
    tipo: TipoAporte
    descripcion: str = Field(min_length=1, max_length=2000)
    cantidad_ofrecida: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    unidad: str = Field(min_length=1, max_length=40)
    aportes: list[AporteRequest] = Field(default_factory=list)

    @model_validator(mode="after")
    def validar_aportes(self) -> "OfertaItemRequest":
        if len({a.recurso_nacional_id for a in self.aportes}) != len(self.aportes):
            raise ValueError("No se puede repetir un recurso en el mismo lote.")
        if (
            self.aportes
            and sum(a.cantidad for a in self.aportes) != self.cantidad_ofrecida
        ):
            raise ValueError(
                "La suma de recursos debe coincidir con la cantidad ofrecida."
            )
        return self

    @field_validator("descripcion", "unidad", mode="before")
    @classmethod
    def recortar_texto(cls, valor: object) -> object:
        return valor.strip() if isinstance(valor, str) else valor


class OfertaContenidoRequest(BaseModel):
    """Contenido versionable de una oferta sobre uno o más lotes."""

    observaciones: str | None = Field(default=None, max_length=4000)
    items: list[OfertaItemRequest] = Field(min_length=1)

    @field_validator("observaciones", mode="before")
    @classmethod
    def recortar_observaciones(cls, valor: object) -> object:
        return valor.strip() if isinstance(valor, str) else valor

    @model_validator(mode="after")
    def rechazar_lotes_duplicados(self) -> "OfertaContenidoRequest":
        ids = [item.lote_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("La oferta no puede repetir el mismo lote.")
        return self


class OfertaCreateRequest(OfertaContenidoRequest):
    """Nueva oferta de la ONG autenticada para una convocatoria."""

    convocatoria_id: int = Field(gt=0)


class OfertaUpdateRequest(OfertaContenidoRequest):
    """Nueva versión del contenido de una oferta existente."""

    version_bloqueo: int = Field(gt=0)


class OfertaItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lote_id: int
    tipo: TipoAporte
    descripcion: str
    cantidad_ofrecida: Decimal
    unidad: str
    aportes: list["AporteResponse"] = Field(default_factory=list)


class AporteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ong_id: int
    recurso_nacional_id: UUID
    capacidad_nacional_id: UUID
    cantidad: Decimal
    unidad: str


class ParticipanteResponse(BaseModel):
    ong_id: int
    nombre: str
    rol: TipoParticipacion
    confirmada: bool


class ConsorcioRequest(BaseModel):
    version_bloqueo: int = Field(gt=0)
    ong_ids: list[int] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def validar_integrantes(self) -> "ConsorcioRequest":
        if any(i <= 0 for i in self.ong_ids) or len(set(self.ong_ids)) != len(
            self.ong_ids
        ):
            raise ValueError("Las ONGs deben ser distintas y válidas.")
        return self


class ConfirmacionConsorcioRequest(BaseModel):
    version_bloqueo: int = Field(gt=0)


class OngConsorcioResponse(BaseModel):
    ong_id: int
    nombre: str


class OfertaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    convocatoria_id: int
    emergencia_id: int
    ong_creadora_id: int
    creada_por_usuario_id: int
    estado: EstadoOferta
    version_actual: int
    version_bloqueo: int
    editable: bool
    observaciones: str | None
    presentada_en: AwareDatetime | None
    creada_en: AwareDatetime
    items: list[OfertaItemResponse]
    participantes: list[ParticipanteResponse] = Field(default_factory=list)
    requiere_desglose_nacional: bool = False
    consorcio_editable: bool = False


class OfertaPropiaResponse(OfertaResponse):
    """Oferta propia con el contexto de la emergencia para mostrarla sin IDs."""

    emergencia: EmergenciaResumenResponse
