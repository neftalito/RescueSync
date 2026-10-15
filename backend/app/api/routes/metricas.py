"""Consultas globales de solo lectura exclusivas de auditoría y dirección."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import ClienteBonitaDep, requerir_operacion
from app.core.permissions import OperacionProtegida
from app.db.models import Usuario
from app.db.session import get_db
from app.schemas import ErrorResponse
from app.schemas.metricas import FiltrosMetricas, ReporteMetricas, ReporteTiempos
from app.services.metricas import obtener_metricas
from app.services.metricas_bonita import obtener_tiempos

router = APIRouter()
UsuarioAuditor = Annotated[
    Usuario, Depends(requerir_operacion(OperacionProtegida.CONSULTAR_METRICAS))
]
Filtros = Annotated[FiltrosMetricas, Query()]
BaseDatos = Annotated[Session, Depends(get_db)]
ERRORES = {codigo: {"model": ErrorResponse} for codigo in (401, 403, 422)}


@router.get(
    "",
    response_model=ReporteMetricas,
    responses=ERRORES,
    summary="Consultar indicadores globales",
    description="Solo AUDITOR_DIRECTIVO. Filtra por fecha de alta de la emergencia; los datos relacionados reflejan su situación actual. Las fechas son inclusivas en America/Argentina/Buenos_Aires.",
)
def consultar_metricas(
    filtros: Filtros, session: BaseDatos, _usuario: UsuarioAuditor
) -> ReporteMetricas:
    """Devuelve agregados locales sin depender de la disponibilidad de Bonita."""
    return obtener_metricas(session, filtros)


@router.get(
    "/tiempos",
    response_model=ReporteTiempos,
    responses=ERRORES,
    summary="Consultar tiempos por tarea de Bonita",
    description="Solo AUDITOR_DIRECTIVO. Promedios de tareas completadas con inicio observable, agrupados por nombre BPM y versión. Informa cobertura y fallos parciales sin sustituir datos ausentes por cero.",
)
def consultar_tiempos(
    filtros: Filtros,
    session: BaseDatos,
    _usuario: UsuarioAuditor,
    cliente: ClienteBonitaDep,
) -> ReporteTiempos:
    """Informa tiempos y cobertura de las consultas al historial del motor."""
    return obtener_tiempos(session, filtros, cliente)
