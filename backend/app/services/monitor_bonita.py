"""Observa errores del motor sin ejecutar tareas ni temporizadores del proceso."""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import Emergencia, Notificacion
from app.db.session import SessionLocal
from app.integrations.bonita.cliente import ClienteBonita, ErrorBonita
from app.schemas.notificacion import NotificacionResponse
from app.services.notificaciones import notificar_tarea_bonita_fallida
from app.services.tiempo_real import GestorTiempoReal

LOGGER = logging.getLogger(__name__)


def comprobar_tareas_bonita(
    session: Session, cliente: ClienteBonita
) -> list[NotificacionResponse]:
    """Correlaciona fallos con casos propios y confirma las alertas antes de emitirlas."""
    emergencias = dict(
        session.execute(
            select(Emergencia.bonita_process_instance_id, Emergencia.id).where(
                Emergencia.bonita_process_instance_id.is_not(None)
            )
        ).all()
    )
    if not emergencias:
        return []
    nuevas: list[Notificacion] = []
    for tarea in cliente.listar_tareas_fallidas():
        emergencia_id = emergencias.get(tarea.root_case_id)
        if emergencia_id is not None:
            nuevas.extend(
                notificar_tarea_bonita_fallida(
                    session,
                    tarea_id=tarea.id,
                    emergencia_id=emergencia_id,
                    nombre=tarea.name,
                )
            )
    session.commit()
    return [NotificacionResponse.model_validate(n) for n in nuevas]


def _sondear(cliente: ClienteBonita, gestor: GestorTiempoReal) -> None:
    with SessionLocal() as session:
        gestor.programar(comprobar_tareas_bonita(session, cliente))
    gestor.programar_metricas()


async def monitorizar_bonita(
    cliente: ClienteBonita,
    gestor: GestorTiempoReal,
    detener: asyncio.Event,
    intervalo: float,
) -> None:
    """Sondea inmediatamente y luego espera; el apagado aguarda el I/O antes de cerrar clientes."""
    while not detener.is_set():
        try:
            await asyncio.to_thread(_sondear, cliente, gestor)
        except (ErrorBonita, SQLAlchemyError):
            # No publicar trazas HTTP/SQL que puedan contener información sensible.
            LOGGER.warning("No se pudo completar el monitoreo de tareas de Bonita.")
        try:
            await asyncio.wait_for(detener.wait(), timeout=intervalo)
        except TimeoutError:
            pass
