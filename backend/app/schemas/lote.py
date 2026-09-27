"""Esquemas HTTP para crear y editar lotes de necesidades en borrador."""

from decimal import Decimal
from typing import Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.db.models.enums import EstadoLote


class LoteItem(BaseModel):
    """Un lote a crear (sin `id`) o editar (con `id`) dentro de una emergencia."""

    id: int | None = Field(default=None, gt=0)
    version: int | None = Field(default=None, gt=0)
    tipo_necesidad: str = Field(min_length=1, max_length=120)
    descripcion: str | None = Field(default=None, max_length=2000)
    cantidad_requerida: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    unidad: str = Field(min_length=1, max_length=40)

    @field_validator("tipo_necesidad", "unidad", mode="before")
    @classmethod
    def recortar_texto(cls, valor: object) -> object:
        """Elimina espacios accidentales para rechazar textos solo con blancos."""

        return valor.strip() if isinstance(valor, str) else valor

    @field_validator("descripcion", mode="before")
    @classmethod
    def recortar_descripcion(cls, valor: object) -> object:
        """Normaliza la descripción opcional sin convertir vacíos en nulos."""

        return valor.strip() if isinstance(valor, str) else valor

    @model_validator(mode="after")
    def exigir_version_al_editar(self) -> Self:
        """Vincula la versión optimista con la identidad de un lote existente."""

        if (self.id is None) != (self.version is None):
            raise ValueError(
                "Los lotes existentes requieren id y versión; los nuevos no los usan."
            )
        return self


class LotesRequest(BaseModel):
    """Uno o más lotes a guardar en borrador sin publicar la convocatoria."""

    lotes: list[LoteItem] = Field(min_length=1)


class LoteResponse(BaseModel):
    """Lote persistido en estado borrador con su vínculo a la emergencia."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    emergencia_id: int
    creado_por_usuario_id: int
    tipo_necesidad: str
    descripcion: str | None
    cantidad_requerida: Decimal
    unidad: str
    estado: EstadoLote
    version: int
    creado_en: AwareDatetime
    actualizado_en: AwareDatetime
