"""Completa en Bonita la tarea humana `Generar lotes de necesidades`.

La convocatoria ya quedó confirmada en PostgreSQL antes de llamar a esta
función: acá solo se sincroniza con Bonita, en una transacción separada de
la publicación local, sin reintentar ciego un resultado incierto.
"""

from datetime import UTC, datetime

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

    Es segura de reintentar: antes de ejecutar la tarea vuelve a preguntarle
    a Bonita si sigue lista, así que un resultado incierto de un intento
    anterior se reconcilia solo en el siguiente intento.

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

    try:
        tarea = cliente.buscar_tarea_lista(
            emergencia.bonita_process_instance_id, TAREA_GENERAR_LOTES
        )
        if tarea is not None:
            cliente.ejecutar_tarea(tarea.id, USUARIO_ACTOR_COORDINADOR)
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
