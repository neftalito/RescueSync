"""Análisis informativo nacional: recursos declarados sin permisos por riesgo."""

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, Field

from app.schemas.bonita import CantidadExacta
from app.schemas.inventario import ContratoNacional


class EstadoOng(StrEnum):
    PENDIENTE = "PENDIENTE"
    HABILITADA = "HABILITADA"
    SUSPENDIDA = "SUSPENDIDA"
    BAJA = "BAJA"


class TipoRecurso(StrEnum):
    PERSONAL = "PERSONAL"
    VEHICULO = "VEHICULO"
    EQUIPAMIENTO = "EQUIPAMIENTO"
    SUMINISTRO = "SUMINISTRO"


type CantidadPerfil = Annotated[
    CantidadExacta, Field(ge=0, decimal_places=3, allow_inf_nan=False)
]


class CapacidadDeclarada(ContratoNacional):
    capacidad_id: UUID
    codigo: str
    nombre: str
    tipo: TipoRecurso
    unidad: str
    admite_fracciones: bool
    cantidad_total: CantidadPerfil
    cantidad_comprometida: CantidadPerfil
    cantidad_disponible: CantidadPerfil


class PerfilCompetencia(ContratoNacional):
    ong_id: UUID
    nombre: str
    estado_ong: EstadoOng
    evaluado_en: AwareDatetime
    capacidades_declaradas: list[CapacidadDeclarada]
