"""Filtros y resultados públicos de los indicadores globales de RescueSync."""

from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, model_validator

from app.db.models.enums import EstadoEmergencia, GravedadEmergencia

ZONA_REPORTES = ZoneInfo("America/Argentina/Buenos_Aires")


def hoy_reporte() -> date:
    """Resuelve la fecha civil usada por el dashboard, independientemente del host."""
    return datetime.now(ZONA_REPORTES).date()


class FiltrosMetricas(BaseModel):
    """Selecciona emergencias por su fecha de alta y atributos vigentes."""

    fecha_desde: date = Field(default_factory=lambda: hoy_reporte().replace(day=1))
    fecha_hasta: date = Field(default_factory=hoy_reporte)
    municipio_id: int | None = Field(default=None, gt=0)
    gravedad: GravedadEmergencia | None = None
    estado: EstadoEmergencia | None = None

    @model_validator(mode="after")
    def validar_periodo(self) -> Self:
        """Impide períodos invertidos y el desbordamiento del límite superior."""
        if self.fecha_desde > self.fecha_hasta:
            raise ValueError(
                "La fecha desde debe ser anterior o igual a la fecha hasta."
            )
        if self.fecha_hasta == date.max:
            raise ValueError("La fecha hasta debe ser anterior a 9999-12-31.")
        return self


class ConteoMetrica(BaseModel):
    categoria: str
    cantidad: int


class MunicipioMetrica(BaseModel):
    id: int
    nombre: str


class ResumenMetricas(BaseModel):
    emergencias: int
    activas: int
    resueltas: int
    convocatorias_abiertas: int
    ofertas_presentadas: int
    ong_participantes: int


class CantidadOfrecida(BaseModel):
    capacidad: str
    codigo_capacidad: str | None
    unidad: str
    cantidad: Decimal


class ReporteMetricas(BaseModel):
    generado_en: datetime = Field(default_factory=lambda: datetime.now(UTC))
    filtros: FiltrosMetricas
    municipios: list[MunicipioMetrica]
    resumen: ResumenMetricas
    por_estado: list[ConteoMetrica]
    por_gravedad: list[ConteoMetrica]
    evolucion_mensual: list[ConteoMetrica]
    tipos_oferta: list[ConteoMetrica]
    cantidades_ofrecidas: list[CantidadOfrecida]


class DisponibilidadBonita(StrEnum):
    """Distingue ausencia de muestras de un fallo al consultar el historial."""

    DISPONIBLE = "DISPONIBLE"
    PARCIAL = "PARCIAL"
    NO_DISPONIBLE = "NO_DISPONIBLE"
    SIN_DATOS = "SIN_DATOS"


class TiempoEtapa(BaseModel):
    etapa: str
    version_proceso: str
    promedio_segundos: float
    muestras: int


class ReporteTiempos(BaseModel):
    generado_en: datetime = Field(default_factory=lambda: datetime.now(UTC))
    filtros: FiltrosMetricas
    disponibilidad: DisponibilidadBonita
    casos_seleccionados: int
    casos_vinculados: int
    casos_consultados: int
    casos_con_muestras: int
    casos_sin_historial_suficiente: int
    casos_con_error: int
    muestras_descartadas: int
    etapas: list[TiempoEtapa]
