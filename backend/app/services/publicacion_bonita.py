"""Completa en Bonita la tarea humana `Generar lotes de necesidades`.

La convocatoria ya quedó confirmada en PostgreSQL antes de llamar a esta
función: acá solo se sincroniza con Bonita. Ninguna transacción de escritura
queda abierta durante la llamada HTTP (ver `docs/modelo-base-datos-
rescuesync.md`, sección 7.1): primero se reclama el intento en una
transacción corta, después se llama a Bonita sin ningún lock, y por último
se intenta persistir el resultado.

El reclamo (`EN_PROGRESO` + un `claim_id` propio de este intento) evita que
dos intentos concurrentes ejecuten la misma tarea dos veces, y la
persistencia final solo se aplica si ese `claim_id` sigue vigente: si otro
intento ya retomó el reclamo (por ejemplo porque este se pasó de la ventana
de 60s) y ya escribió su propio resultado, este intento no lo pisa.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, update
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

RECLAMO_VIGENTE_DURANTE = timedelta(seconds=60)
"""Ventana en la que un reclamo `EN_PROGRESO` bloquea a otros intentos.

Tiene que cubrir con margen el peor caso de `ClienteBonita` (login +
búsqueda + asignación + ejecución, con un reintento de sesión incluido).
Pasado ese tiempo, un reclamo sin resolver se considera abandonado y un
nuevo intento puede tomarlo — el `claim_id` evita que el intento original,
si igual llega a terminar más tarde, pise el resultado del nuevo dueño.
"""


def completar_generacion_lotes(
    session: Session,
    emergencia: Emergencia,
    convocatoria: Convocatoria,
    cliente: ClienteBonita,
) -> Convocatoria:
    """Completa `Generar lotes de necesidades` del caso vinculado a la emergencia.

    Si no se puede reclamar el intento (ya está `COMPLETADA`, o hay un
    reclamo `EN_PROGRESO` vigente de otro intento concurrente) devuelve la
    convocatoria tal cual, sin tocar Bonita.

    Si Bonita no encuentra la tarea lista, solo se interpreta como éxito
    cuando el intento que se está resolviendo venía de un resultado incierto
    (`RESULTADO_DESCONOCIDO`) o de un reclamo abandonado (`EN_PROGRESO`
    vencido) **y** el archivo de Bonita confirma que la tarea llegó a
    `completed` — no alcanza con que ya no esté `ready`, porque asignarla
    (sin ejecutarla) también la saca de ese estado. Si nunca se había
    intentado, el intento previo falló de forma definitiva, o el archivo no
    confirma la ejecución, se trata como error.

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

    reclamo = _reclamar_intento(session, convocatoria.id)
    if reclamo is None:
        return session.scalar(
            select(Convocatoria).where(Convocatoria.id == convocatoria.id)
        )
    convocatoria, claim_id, reconciliando_resultado_incierto = reclamo

    if (
        emergencia.bonita_sync is not EstadoSincronizacionBonita.VINCULADA
        or emergencia.bonita_process_instance_id is None
    ):
        return _persistir(
            session,
            convocatoria.id,
            claim_id,
            EstadoTareaBonita.ERROR,
            "La emergencia no está vinculada a un caso de Bonita.",
        )

    case_id = emergencia.bonita_process_instance_id
    try:
        tarea = cliente.buscar_tarea_lista(case_id, TAREA_GENERAR_LOTES)
        if tarea is not None:
            cliente.ejecutar_tarea(tarea.id, USUARIO_ACTOR_COORDINADOR)
        elif not (
            reconciliando_resultado_incierto
            and cliente.tarea_completada(case_id, TAREA_GENERAR_LOTES)
        ):
            return _persistir(
                session,
                convocatoria.id,
                claim_id,
                EstadoTareaBonita.ERROR,
                "No se encontró la tarea 'Generar lotes de necesidades' lista "
                "ni confirmada como completada en el caso; puede que el "
                "proceso todavía no haya llegado a ese paso o se haya "
                "resuelto de otra forma.",
            )
    except BonitaResultadoDesconocidoError as error:
        return _persistir(
            session,
            convocatoria.id,
            claim_id,
            EstadoTareaBonita.RESULTADO_DESCONOCIDO,
            str(error),
        )
    except ErrorBonita as error:
        return _persistir(
            session, convocatoria.id, claim_id, EstadoTareaBonita.ERROR, str(error)
        )

    return _persistir(
        session, convocatoria.id, claim_id, EstadoTareaBonita.COMPLETADA, None
    )


def _reclamar_intento(
    session: Session, convocatoria_id: int
) -> tuple[Convocatoria, str, bool] | None:
    """Reclama, bajo un lock breve, el intento de sincronización.

    No llama a Bonita: solo decide si este intento puede proceder y, si
    puede, marca `EN_PROGRESO` con un `claim_id` propio y libera el lock.

    Returns:
        `None` si no hay nada para hacer (ya completada) o si otro intento
        tiene un reclamo vigente. Si puede proceder, una tupla con la
        convocatoria reclamada, el `claim_id` de este intento, y si
        corresponde reconciliar un resultado previo incierto (resultado
        desconocido o reclamo abandonado).
    """

    convocatoria = session.scalar(
        select(Convocatoria).where(Convocatoria.id == convocatoria_id).with_for_update()
    )
    estado_previo = convocatoria.bonita_generar_lotes_estado
    ahora = datetime.now(UTC)

    if estado_previo is EstadoTareaBonita.COMPLETADA:
        session.commit()
        return None

    if estado_previo is EstadoTareaBonita.EN_PROGRESO:
        intento_previo = convocatoria.bonita_generar_lotes_ultimo_intento_en
        reclamo_vigente = (
            intento_previo is not None
            and ahora - intento_previo < RECLAMO_VIGENTE_DURANTE
        )
        if reclamo_vigente:
            session.commit()
            return None

    reconciliando = estado_previo in (
        EstadoTareaBonita.RESULTADO_DESCONOCIDO,
        EstadoTareaBonita.EN_PROGRESO,
    )
    claim_id = uuid4().hex
    convocatoria.bonita_generar_lotes_estado = EstadoTareaBonita.EN_PROGRESO
    convocatoria.bonita_generar_lotes_ultimo_intento_en = ahora
    convocatoria.bonita_generar_lotes_claim_id = claim_id
    session.commit()
    session.refresh(convocatoria)
    return convocatoria, claim_id, reconciliando


def _persistir(
    session: Session,
    convocatoria_id: int,
    claim_id: str,
    estado: EstadoTareaBonita,
    mensaje: str | None,
) -> Convocatoria:
    """Guarda el resultado solo si este intento sigue siendo dueño del reclamo.

    Si otro intento ya retomó el reclamo (y probablemente ya escribió su
    propio resultado), esta escritura no afecta ninguna fila: se devuelve el
    estado vigente tal cual, sin pisarlo.
    """

    session.execute(
        update(Convocatoria)
        .where(
            Convocatoria.id == convocatoria_id,
            Convocatoria.bonita_generar_lotes_claim_id == claim_id,
        )
        .values(
            bonita_generar_lotes_estado=estado,
            bonita_generar_lotes_ultimo_error=mensaje,
            bonita_generar_lotes_ultimo_intento_en=datetime.now(UTC),
        )
    )
    session.commit()
    return session.scalar(
        select(Convocatoria).where(Convocatoria.id == convocatoria_id)
    )
