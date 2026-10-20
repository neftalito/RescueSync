"""Contrato de capacidades certificado histórico; sólo para leer evaluaciones v2."""

from uuid import UUID

from app.db.models.enums import GravedadEmergencia
from app.schemas.inventario import ContratoNacional


class CapacidadHabilitadaResponse(ContratoNacional):
    capacidad_id: UUID
    codigo: str
    nombre: str
    unidad: str
    riesgo_maximo: GravedadEmergencia
    niveles_riesgo_permitidos: list[GravedadEmergencia]
    acreditacion_ids: list[UUID]
