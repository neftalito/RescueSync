"""Despacha contratos fuera de locks y reconcilia la misma actividad tras timeout."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EstadoTareaBonita
from app.db.models.ejecucion import ComandoBonita
from app.integrations.bonita.cliente import (
    BonitaResultadoDesconocidoError,
    ClienteBonita,
    ErrorBonita,
)
from app.schemas.ejecucion import DespachoResponse
from app.services.evaluaciones import IntegracionLocalError, bloquear_emergencia


def despachar(
    session: Session, identidad: UUID, cliente: ClienteBonita
) -> DespachoResponse:
    """El retry conserva contrato e ID; jamás ejecuta otra actividad del mismo nombre."""
    comando = session.get(ComandoBonita, identidad)
    if comando is None:
        raise IntegracionLocalError("El comando no existe.", 404)
    emergencia_id = comando.emergencia_id
    e = bloquear_emergencia(session, emergencia_id)
    comando = session.scalar(
        select(ComandoBonita)
        .where(ComandoBonita.id == identidad)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    ahora = datetime.now(UTC)
    if comando.estado == EstadoTareaBonita.COMPLETADA or (
        comando.estado == EstadoTareaBonita.EN_PROGRESO
        and comando.intento_en is not None
        and ahora - comando.intento_en < timedelta(minutes=2)
    ):
        session.commit()
        return respuesta(comando)
    case_id = e.bonita_process_instance_id
    tarea_id = comando.tarea_id
    tarea, actor, contrato, correlacion = (
        comando.tarea,
        comando.actor,
        comando.contrato,
        comando.correlacion,
    )
    claim = uuid4()
    comando.claim_id = claim
    comando.estado = EstadoTareaBonita.EN_PROGRESO
    comando.intento_en = ahora
    session.commit()
    estado, error = EstadoTareaBonita.COMPLETADA, None
    try:
        if case_id is None:
            raise IntegracionLocalError(
                "La emergencia no tiene un caso Bonita vinculado."
            )
        if tarea_id is not None and cliente.actividad_completada(tarea_id, case_id):
            pass
        else:
            participante = tarea == "Marcar como finalizada la tarea"
            incidente = tarea.startswith("Atender incidente de ")
            if tarea_id is None:
                candidatas = cliente.tareas_para_comando(case_id, tarea)
                candidatas = [
                    t
                    for t in candidatas
                    if tarea == "Marcar proyecto como terminado"
                    or cliente.variable_correlacion(
                        case_id, t.id, participante, operacion=incidente
                    )
                    == correlacion
                ]
                if len(candidatas) != 1:
                    raise IntegracionLocalError(
                        "No hay una única actividad de Bonita correlacionada. Revisá la configuración del proceso."
                    )
                tarea_id = candidatas[0].id
                # Persistir el ID antes de ejecutar para recuperar una respuesta perdida.
                bloquear_emergencia(session, emergencia_id)
                comando = session.get(ComandoBonita, identidad)
                if comando.claim_id != claim:
                    return respuesta(comando)
                otro = session.scalar(
                    select(ComandoBonita.id).where(
                        ComandoBonita.tarea_id == tarea_id,
                        ComandoBonita.id != identidad,
                    )
                )
                if otro is not None:
                    raise IntegracionLocalError(
                        "La actividad ya pertenece a otra intención pendiente."
                    )
                comando.tarea_id = tarea_id
                session.commit()
            cliente.tarea_exacta(tarea_id, case_id, tarea)
            cliente.ejecutar_tarea(tarea_id, actor, contrato)
    except BonitaResultadoDesconocidoError:
        estado, error = (
            EstadoTareaBonita.RESULTADO_DESCONOCIDO,
            "Bonita pudo haber completado la actividad. Reintentá para reconciliar la misma intención.",
        )
    except (ErrorBonita, IntegracionLocalError):
        estado, error = (
            EstadoTareaBonita.ERROR,
            "No se pudo completar la actividad correlacionada de Bonita. La intención quedó guardada para reintentar.",
        )
    session.expire_all()
    bloquear_emergencia(session, emergencia_id)
    comando = session.get(ComandoBonita, identidad)
    if comando.claim_id == claim:
        comando.estado, comando.error = estado, error
        session.commit()
    return respuesta(comando)


def respuesta(comando: ComandoBonita) -> DespachoResponse:
    return DespachoResponse(
        comando_id=comando.id, estado=comando.estado.value, error=comando.error
    )
