"""Catálogo, credenciales verificadas y perfiles calculados sin reservar recursos."""

from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime

from app.schemas.inventario import ContratoNacional


class EstadoAcreditacion(StrEnum):
    OTORGADA = "OTORGADA"
    REVOCADA = "REVOCADA"


class EstadoOng(StrEnum):
    PENDIENTE = "PENDIENTE"
    HABILITADA = "HABILITADA"
    SUSPENDIDA = "SUSPENDIDA"
    BAJA = "BAJA"


class NivelRiesgo(StrEnum):
    BAJA = "BAJA"
    MEDIA = "MEDIA"
    ALTA = "ALTA"
    CRITICA = "CRITICA"


class TipoRecurso(StrEnum):
    PERSONAL = "PERSONAL"
    VEHICULO = "VEHICULO"
    EQUIPAMIENTO = "EQUIPAMIENTO"
    SUMINISTRO = "SUMINISTRO"


class EstadoVigencia(StrEnum):
    FUTURA = "FUTURA"
    VIGENTE = "VIGENTE"
    VENCIDA = "VENCIDA"
    REVOCADA = "REVOCADA"


class CodigoMotivo(StrEnum):
    ACREDITACION_FUTURA = "ACREDITACION_FUTURA"
    ACREDITACION_VENCIDA = "ACREDITACION_VENCIDA"
    ACREDITACION_REVOCADA = "ACREDITACION_REVOCADA"
    CERTIFICACION_INACTIVA = "CERTIFICACION_INACTIVA"
    CAPACIDAD_INACTIVA = "CAPACIDAD_INACTIVA"
    ONG_PENDIENTE = "ONG_PENDIENTE"
    ONG_SUSPENDIDA = "ONG_SUSPENDIDA"
    ONG_BAJA = "ONG_BAJA"


class MotivoResponse(ContratoNacional):
    codigo: CodigoMotivo
    mensaje: str
    capacidad_id: UUID | None = None


class AlcanceResponse(ContratoNacional):
    capacidad_id: UUID
    codigo: str
    nombre: str
    tipo: TipoRecurso
    unidad: str
    admite_fracciones: bool
    activa: bool
    riesgo_maximo: NivelRiesgo


class CertificacionResponse(ContratoNacional):
    id: UUID
    codigo: str
    revision: int
    nombre: str
    activa: bool
    alcances: list[AlcanceResponse]


class AcreditacionResponse(ContratoNacional):
    id: UUID
    certificacion: CertificacionResponse
    emisor: str
    numero_credencial: str
    vigente_desde: AwareDatetime
    vigente_hasta: AwareDatetime
    estado: EstadoAcreditacion
    estado_vigencia: EstadoVigencia
    revocada_en: AwareDatetime | None
    motivo_revocacion: str | None
    motivos: list[MotivoResponse]


class CapacidadHabilitadaResponse(ContratoNacional):
    capacidad_id: UUID
    codigo: str
    nombre: str
    unidad: str
    riesgo_maximo: NivelRiesgo
    niveles_riesgo_permitidos: list[NivelRiesgo]
    acreditacion_ids: list[UUID]


class CertificacionesOngResponse(ContratoNacional):
    ong_id: UUID
    estado_ong: EstadoOng
    evaluado_en: AwareDatetime
    acreditaciones: list[AcreditacionResponse]
    capacidades_habilitadas: list[CapacidadHabilitadaResponse]
    motivos_institucionales: list[MotivoResponse]
