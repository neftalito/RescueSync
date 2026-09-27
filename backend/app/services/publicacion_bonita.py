"""Completa en Bonita la tarea humana `Generar lotes de necesidades`.

La publicación local ya está confirmada cuando empieza este caso de uso. Cada
intento toma un claim persistido en una transacción corta, llama a Bonita sin
una transacción PostgreSQL abierta y guarda el resultado en otra transacción.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Convocatoria, EstadoSincronizacionBonita
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

_DURACION_CLAIM_MINIMA = timedelta(minutes=15)
_MARGEN_SOLICITUDES_HTTP = 20


@dataclass(frozen=True)
class _IntentoSincronizacion:
    """Datos inmutables necesarios durante la llamada externa sin transacción."""

    id: UUID
    convocatoria_id: int
    case_id: int
    reconciliando_resultado_incierto: bool


def completar_generacion_lotes(
    session: Session,
    convocatoria: Convocatoria,
    cliente: ClienteBonita,
) -> Convocatoria:
    """Completa `Generar lotes de necesidades` sin duplicar intentos concurrentes.

    Un claim vigente hace que los demás reintentos devuelvan de inmediato el
    último estado estable, sin consultar ni ejecutar la tarea. Si el proceso se
    interrumpe después de tomar el claim, otro pedido puede recuperarlo una vez
    vencida una ventana calculada por encima de los timeouts HTTP configurados.

    Si Bonita no encuentra la tarea lista, solo se interpreta como éxito cuando
    se está reconciliando un `RESULTADO_DESCONOCIDO`. En un primer intento puede
    significar que el caso todavía no llegó a ese paso.

    Args:
        session: Sesión SQLAlchemy usada en las transacciones locales breves.
        convocatoria: Convocatoria publicada que debe avanzar en Bonita.
        cliente: Cliente Bonita compartido de la aplicación.

    Returns:
        La convocatoria con el último resultado estable conocido.
    """

    toma = _tomar_intento(session, convocatoria.id, cliente)
    if isinstance(toma, Convocatoria):
        return toma

    try:
        tarea = cliente.buscar_tarea_lista(toma.case_id, TAREA_GENERAR_LOTES)
        if tarea is not None:
            resultado_concurrente = _marcar_ejecucion_iniciada(session, toma)
            if resultado_concurrente is not None:
                return resultado_concurrente
            cliente.ejecutar_tarea(tarea.id, USUARIO_ACTOR_COORDINADOR)
        elif not toma.reconciliando_resultado_incierto:
            return _persistir_resultado(
                session,
                toma,
                EstadoTareaBonita.ERROR,
                "No se encontró la tarea 'Generar lotes de necesidades' lista "
                "en el caso; puede que el proceso todavía no haya llegado a "
                "ese paso o se haya resuelto de otra forma.",
            )
    except BonitaResultadoDesconocidoError as error:
        return _persistir_resultado(
            session,
            toma,
            EstadoTareaBonita.RESULTADO_DESCONOCIDO,
            str(error),
        )
    except ErrorBonita as error:
        return _persistir_resultado(
            session,
            toma,
            EstadoTareaBonita.ERROR,
            str(error),
        )

    return _persistir_resultado(
        session,
        toma,
        EstadoTareaBonita.COMPLETADA,
        None,
    )


def _tomar_intento(
    session: Session,
    convocatoria_id: int,
    cliente: ClienteBonita,
) -> _IntentoSincronizacion | Convocatoria:
    """Toma y confirma un claim, o devuelve la convocatoria sin llamar a Bonita."""

    convocatoria = session.scalar(
        select(Convocatoria).where(Convocatoria.id == convocatoria_id).with_for_update()
    )
    if convocatoria is None:
        raise RuntimeError("La convocatoria desapareció durante la sincronización.")

    if convocatoria.bonita_generar_lotes_estado is EstadoTareaBonita.COMPLETADA:
        _liberar_claim(convocatoria)
        session.commit()
        return convocatoria

    ahora = datetime.now(UTC)
    if (
        convocatoria.bonita_generar_lotes_intento_id is not None
        and convocatoria.bonita_generar_lotes_intento_expira_en is not None
        and convocatoria.bonita_generar_lotes_intento_expira_en > ahora
    ):
        session.commit()
        return convocatoria

    emergencia = convocatoria.emergencia
    if (
        emergencia.bonita_sync is not EstadoSincronizacionBonita.VINCULADA
        or emergencia.bonita_process_instance_id is None
    ):
        convocatoria.bonita_generar_lotes_estado = EstadoTareaBonita.ERROR
        convocatoria.bonita_generar_lotes_ultimo_error = (
            "La emergencia no está vinculada a un caso de Bonita."
        )
        convocatoria.bonita_generar_lotes_ultimo_intento_en = ahora
        _liberar_claim(convocatoria)
        session.commit()
        return convocatoria

    intento_id = uuid4()
    intento = _IntentoSincronizacion(
        id=intento_id,
        convocatoria_id=convocatoria.id,
        case_id=emergencia.bonita_process_instance_id,
        reconciliando_resultado_incierto=(
            convocatoria.bonita_generar_lotes_estado
            is EstadoTareaBonita.RESULTADO_DESCONOCIDO
        ),
    )
    convocatoria.bonita_generar_lotes_intento_id = intento_id
    convocatoria.bonita_generar_lotes_intento_expira_en = ahora + _duracion_claim(
        cliente
    )
    session.commit()
    return intento


def _marcar_ejecucion_iniciada(
    session: Session,
    intento: _IntentoSincronizacion,
) -> Convocatoria | None:
    """Persiste la ambigüedad antes de ejecutar la operación no idempotente."""

    convocatoria = session.scalar(
        select(Convocatoria)
        .where(Convocatoria.id == intento.convocatoria_id)
        .with_for_update()
    )
    if convocatoria is None:
        raise RuntimeError("La convocatoria desapareció durante la sincronización.")

    if convocatoria.bonita_generar_lotes_intento_id != intento.id:
        session.commit()
        return convocatoria

    convocatoria.bonita_generar_lotes_estado = EstadoTareaBonita.RESULTADO_DESCONOCIDO
    convocatoria.bonita_generar_lotes_ultimo_error = (
        "La ejecución de la tarea está en curso; si se interrumpe, debe reconciliarse."
    )
    convocatoria.bonita_generar_lotes_ultimo_intento_en = datetime.now(UTC)
    session.commit()
    return None


def _persistir_resultado(
    session: Session,
    intento: _IntentoSincronizacion,
    estado: EstadoTareaBonita,
    mensaje: str | None,
) -> Convocatoria:
    """Guarda el resultado sólo si ningún recuperador reemplazó el claim."""

    convocatoria = session.scalar(
        select(Convocatoria)
        .where(Convocatoria.id == intento.convocatoria_id)
        .with_for_update()
    )
    if convocatoria is None:
        raise RuntimeError("La convocatoria desapareció durante la sincronización.")

    if convocatoria.bonita_generar_lotes_intento_id != intento.id:
        session.commit()
        return convocatoria

    convocatoria.bonita_generar_lotes_estado = estado
    convocatoria.bonita_generar_lotes_ultimo_error = mensaje
    convocatoria.bonita_generar_lotes_ultimo_intento_en = datetime.now(UTC)
    _liberar_claim(convocatoria)
    session.commit()
    session.refresh(convocatoria)
    return convocatoria


def _duracion_claim(cliente: ClienteBonita) -> timedelta:
    """Calcula una ventana mayor al peor recorrido HTTP normal del intento."""

    configuracion = cliente.configuracion
    presupuesto_http = timedelta(
        seconds=(
            configuracion.timeout_conexion_segundos
            + configuracion.timeout_lectura_segundos
        )
        * _MARGEN_SOLICITUDES_HTTP
    )
    return max(_DURACION_CLAIM_MINIMA, presupuesto_http)


def _liberar_claim(convocatoria: Convocatoria) -> None:
    """Limpia en conjunto las dos columnas que representan el claim."""

    convocatoria.bonita_generar_lotes_intento_id = None
    convocatoria.bonita_generar_lotes_intento_expira_en = None
