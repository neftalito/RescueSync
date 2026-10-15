"""Contratos del catálogo nacional administrado a través del backend local."""

from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from app.schemas.inventario import ContratoNacional, Nombre


class UnidadResponse(ContratoNacional):
    codigo: str
    nombre: str


class CapacidadCreate(ContratoNacional):
    codigo: str = Field(min_length=1, max_length=80, pattern=r"^[A-Z][A-Z0-9_]*$")
    nombre: Nombre
    tipo: Literal["PERSONAL", "VEHICULO", "EQUIPAMIENTO", "SUMINISTRO"]
    unidad: str = Field(min_length=1, max_length=40)
    admite_fracciones: bool = Field(default=False, strict=True)

    @field_validator("codigo", "unidad", mode="before")
    @classmethod
    def recortar_texto(cls, valor: object) -> object:
        """Acepta espacios accidentales sin modificar el código de la unidad."""
        return valor.strip() if isinstance(valor, str) else valor

    @model_validator(mode="after")
    def validar_cantidades_discretas(self) -> Self:
        """Rechaza fracciones para personal y vehículos antes de llamar a la API."""
        if self.tipo in {"PERSONAL", "VEHICULO"} and self.admite_fracciones:
            raise ValueError("Personal y vehículos no admiten cantidades fraccionadas.")
        return self
