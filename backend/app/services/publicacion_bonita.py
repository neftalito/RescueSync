"""Completa en Bonita la tarea humana `Generar lotes de necesidades`.

La convocatoria ya quedó confirmada en PostgreSQL antes de llamar a esta
función: acá solo se sincroniza con Bonita. El bloqueo pesimista de la fila
se mantiene durante la llamada a Bonita a propósito, para que dos intentos
concurrentes (por ejemplo, dos reintentos casi simultáneos) queden
serializados por Postgres en vez de pisarse el resultado entre sí.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Convocatoria, Emergencia, EstadoSincronizacionBonita
from app.db.models.enums import EstadoTareaBonita
from app.integrations.bonita.cliente import (
    BonitaResultadoDesconocidoError,
    ClienteBonita,
    ErrorBonita,
)
from app.integrations.bonita.contratos import (
    TAREA_GENERAR_LOTES,
    USUARIO_ACTOR_COORDINADOR,
)


def completar_generacion_lotes(
    session: Session,
    emergencia: Emergencia,
    convocatoria: Convocatoria,
    cliente: ClienteBonita,
) -> Convocatoria:
    """Completa `Generar lotes de necesidades` del caso vinculado a la emergencia.

    Vuelve a leer y bloquear la convocatoria (`SELECT ... FOR UPDATE`) antes
    de decidir si hace falta llamar a Bonita, para que el chequeo de
    "¿ya está completada?" y la persistencia del resultado sean atómicos
    frente a otro intento concurrente sobre la misma fila.

    Si Bonita no encuentra la tarea lista, solo se interpreta como éxito
    (reconciliación) cuando el intento anterior había quedado en
    `RESULTADO_DESCONOCIDO` — mismo criterio que
    `vinculacion_bonita.py::_adoptar_caso_si_existe`. Si nunca se había
    intentado o el intento previo falló de forma definitiva, no encontrar la
    tarea se trata como error: puede significar que el caso todavía no llegó
    a ese paso, no que ya se haya completado.

    Args:
        session: Sesión SQLAlchemy con la que se persiste el resultado.
        emergencia: Emergencia con el vínculo de caso de Bonita ya cargado.
        convocatoria: Convocatoria recién publicada o reutilizada localmente.
        cliente: Cliente Bonita compartido de la aplicación.

    Returns:
        La convocatoria con su estado de sincronización actualizado. Ante
        cualquier fallo de integración la convocatoria se conserva y queda
        un error seguro que permite un reintento trazable.
    """

    convocatoria = session.scalar(
        select(Convocatoria).where(Convocatoria.id == convocatoria.id).with_for_update()
    )
    if convocatoria.bonita_generar_lotes_estado is EstadoTareaBonita.COMPLETADA:
        return convocatoria

    if (
        emergencia.bonita_sync is not EstadoSincronizacionBonita.VINCULADA
        or emergencia.bonita_process_instance_id is None
    ):
        return _persistir(
            session,
            convocatoria,
            EstadoTareaBonita.ERROR,
            "La emergencia no está vinculada a un caso de Bonita.",
        )

    reconciliando_resultado_incierto = (
        convocatoria.bonita_generar_lotes_estado
        is EstadoTareaBonita.RESULTADO_DESCONOCIDO
    )

    try:
        tarea = cliente.buscar_tarea_lista(
            emergencia.bonita_process_instance_id, TAREA_GENERAR_LOTES
        )
        if tarea is not None:
            cliente.ejecutar_tarea(tarea.id, USUARIO_ACTOR_COORDINADOR)
        elif not reconciliando_resultado_incierto:
            return _persistir(
                session,
                convocatoria,
                EstadoTareaBonita.ERROR,
                "No se encontró la tarea 'Generar lotes de necesidades' lista "
                "en el caso; puede que el proceso todavía no haya llegado a "
                "ese paso o se haya resuelto de otra forma.",
            )
    except BonitaResultadoDesconocidoError as error:
        return _persistir(
            session, convocatoria, EstadoTareaBonita.RESULTADO_DESCONOCIDO, str(error)
        )
    except ErrorBonita as error:
        return _persistir(session, convocatoria, EstadoTareaBonita.ERROR, str(error))

    return _persistir(session, convocatoria, EstadoTareaBonita.COMPLETADA, None)


def _persistir(
    session: Session,
    convocatoria: Convocatoria,
    estado: EstadoTareaBonita,
    mensaje: str | None,
) -> Convocatoria:
    """Guarda el resultado de sincronización y el último error seguro."""

    convocatoria.bonita_generar_lotes_estado = estado
    convocatoria.bonita_generar_lotes_ultimo_error = mensaje
    convocatoria.bonita_generar_lotes_ultimo_intento_en = datetime.now(UTC)
    session.commit()
    session.refresh(convocatoria)
    return convocatoria
