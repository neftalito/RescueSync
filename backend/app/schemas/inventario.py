"""DTO del adaptador nacional, con cantidades decimales como strings en JSON."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
)
from pydantic.alias_generators import to_camel


class ContratoNacional(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid"
    )


class ConexionRequest(ContratoNacional):
    identificador_login: str = Field(min_length=1, max_length=320)
    password: SecretStr = Field(min_length=1, max_length=128)


class TokenNacional(BaseModel):
    access_token: SecretStr = Field(min_length=1, max_length=3000)
    token_type: Literal["bearer"]
    expires_in: int = Field(gt=0, le=3600)


class CuentaNacional(ContratoNacional):
    id: UUID
    rol: Literal["ONG", "ADMIN_NACIONAL", "INTEGRACION"]
    ong_id: UUID | None


class EstadoConexion(ContratoNacional):
    vinculada: bool
    conectada: bool
    ong_id: UUID | None
    expira_en: datetime | None = None


class VinculoRequest(BaseModel):
    ong_nacional_id: UUID | None


class CapacidadResponse(ContratoNacional):
    id: UUID
    codigo: str
    nombre: str
    tipo: Literal["PERSONAL", "VEHICULO", "EQUIPAMIENTO", "SUMINISTRO"]
    unidad: str
    admite_fracciones: bool


type Cantidad = Annotated[
    Decimal, Field(ge=0, max_digits=14, decimal_places=3, allow_inf_nan=False)
]
type Nombre = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)
]
type Codigo = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
]


class RecursoCreate(ContratoNacional):
    capacidad_id: UUID
    codigo_interno: Codigo
    nombre: Nombre
    cantidad_total: Cantidad


class RecursoUpdate(ContratoNacional):
    cantidad_total: Cantidad
    actualizado_en: AwareDatetime


class RecursoResponse(ContratoNacional):
    id: UUID
    ong_id: UUID
    capacidad_id: UUID
    codigo_interno: str
    nombre: str
    capacidad: str
    unidad: str
    admite_fracciones: bool
    cantidad_total: Decimal
    cantidad_comprometida: Decimal
    cantidad_disponible: Decimal
    activo: bool
    actualizado_en: datetime
