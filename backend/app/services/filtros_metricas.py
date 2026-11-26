"""Selección común de emergencias para todas las fuentes del dashboard."""

from datetime import UTC, datetime, time, timedelta

from sqlalchemy import Select, select

from app.db.models import Emergencia
from app.schemas.metricas import ZONA_REPORTES, FiltrosEmergenciasMetricas


def emergencias_filtradas(
    filtros: FiltrosEmergenciasMetricas,
) -> Select[tuple[Emergencia]]:
    """Aplica fechas civiles inclusivas convirtiéndolas en límites UTC."""
    desde = datetime.combine(filtros.fecha_desde, time.min, ZONA_REPORTES)
    hasta = datetime.combine(
        filtros.fecha_hasta + timedelta(days=1), time.min, ZONA_REPORTES
    )
    consulta = select(Emergencia).where(
        Emergencia.creada_en >= desde.astimezone(UTC),
        Emergencia.creada_en < hasta.astimezone(UTC),
    )
    if filtros.municipio_id is not None:
        consulta = consulta.where(Emergencia.municipio_id == filtros.municipio_id)
    if filtros.gravedad is not None:
        consulta = consulta.where(Emergencia.gravedad == filtros.gravedad)
    if filtros.estado is not None:
        consulta = consulta.where(Emergencia.estado == filtros.estado)
    return consulta
