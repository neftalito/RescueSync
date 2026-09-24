"""Vinculación trazable entre una emergencia local y su instancia en Bonita.

El alta confirma primero la emergencia en PostgreSQL y recién después inicia
el caso. La llamada HTTP nunca ocurre con una transacción de escritura
abierta: la vinculación se persiste en una transacción posterior. Un POST de
instanciación jamás se repite sin reconciliar antes con
`buscar_casos_por_emergencia`.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import Emergencia, EstadoSincronizacionBonita
from app.integrations.bonita.cliente import (
    BonitaResultadoDesconocidoError,
    ClienteBonita,
    ErrorBonita,
)
from app.integrations.bonita.contratos import ContratoInicioProceso


def vincular_emergencia_con_bonita(
    session: Session,
    emergencia: Emergencia,
    cliente: ClienteBonita,
) -> Emergencia:
    """Inicia la instancia de Bonita y persiste su `caseId` junto al estado.

    Args:
        session: Sesión SQLAlchemy sin transacción de escritura abierta.
        emergencia: Emergencia ya confirmada en la base local.
        cliente: Cliente Bonita compartido de la aplicación.

    Returns:
        La emergencia con su estado de sincronización actualizado. Ante
        cualquier fallo de integración la emergencia se conserva y queda un
        error seguro que permite un reintento trazable.
    """

    if (
        emergencia.bonita_sync is EstadoSincronizacionBonita.VINCULADA
        and emergencia.bonita_process_instance_id is not None
    ):
        return emergencia

    ahora = datetime.now(UTC)
    if emergencia.bonita_sync is EstadoSincronizacionBonita.RESULTADO_DESCONOCIDO:
        try:
            adoptada = _adoptar_caso_si_existe(session, emergencia, cliente, ahora)
        except ErrorBonita as error:
            _persistir_estado(
                session,
                emergencia,
                EstadoSincronizacionBonita.RESULTADO_DESCONOCIDO,
                f"Reconciliación pendiente: {error}",
                ahora,
            )
            return emergencia
        if adoptada:
            return emergencia

    try:
        definicion = cliente.obtener_proceso_habilitado()
        instancia = cliente.iniciar_instancia(
            definicion.id, _contrato_desde(emergencia)
        )
    except BonitaResultadoDesconocidoError as error:
        _resolver_incertidumbre(session, emergencia, cliente, str(error), ahora)
        return emergencia
    except ErrorBonita as error:
        _persistir_estado(
            session,
            emergencia,
            EstadoSincronizacionBonita.ERROR,
            str(error),
            ahora,
        )
        return emergencia

    _persistir_vinculo(
        session,
        emergencia,
        definicion.id,
        instancia.case_id,
        cliente.configuracion.version_proceso,
        ahora,
    )
    return emergencia


def _contrato_desde(emergencia: Emergencia) -> ContratoInicioProceso:
    """Traduce la emergencia al contrato de inicio versionado en el `.bar`."""

    return ContratoInicioProceso.model_validate(
        {
            "idEmergencia": emergencia.id,
            "gravedad": emergencia.gravedad,
            "zona": emergencia.zona,
            "descripcion": emergencia.descripcion,
            "municipioId": emergencia.municipio_id,
        }
    )


def _adoptar_caso_si_existe(
    session: Session,
    emergencia: Emergencia,
    cliente: ClienteBonita,
    ahora: datetime,
) -> bool:
    """Adopta el caso activo de la emergencia sin crear una instancia nueva.

    Returns:
        Verdadero si encontró el caso y persistió la vinculación.
    """

    definicion = cliente.obtener_proceso_habilitado()
    casos = cliente.buscar_casos_por_emergencia(definicion.id, emergencia.id)
    if not casos:
        return False
    _persistir_vinculo(
        session,
        emergencia,
        definicion.id,
        casos[0].id,
        cliente.configuracion.version_proceso,
        ahora,
    )
    return True


def _resolver_incertidumbre(
    session: Session,
    emergencia: Emergencia,
    cliente: ClienteBonita,
    mensaje: str,
    ahora: datetime,
) -> None:
    """Reconcilia un POST incierto antes de permitir cualquier reintento."""

    try:
        adoptada = _adoptar_caso_si_existe(session, emergencia, cliente, ahora)
    except ErrorBonita as error:
        _persistir_estado(
            session,
            emergencia,
            EstadoSincronizacionBonita.RESULTADO_DESCONOCIDO,
            f"{mensaje} Reconciliación pendiente: {error}",
            ahora,
        )
        return
    if not adoptada:
        _persistir_estado(
            session,
            emergencia,
            EstadoSincronizacionBonita.RESULTADO_DESCONOCIDO,
            mensaje,
            ahora,
        )


def _persistir_vinculo(
    session: Session,
    emergencia: Emergencia,
    definicion_id: int,
    case_id: int,
    version_proceso: str,
    ahora: datetime,
) -> None:
    """Guarda el `caseId` validado y marca la sincronización como vinculada."""

    emergencia.bonita_process_definition_id = definicion_id
    emergencia.bonita_process_instance_id = case_id
    emergencia.bonita_process_version = version_proceso
    emergencia.bonita_sync = EstadoSincronizacionBonita.VINCULADA
    emergencia.bonita_ultimo_error = None
    emergencia.bonita_ultimo_intento_en = ahora
    session.commit()
    session.refresh(emergencia)


def _persistir_estado(
    session: Session,
    emergencia: Emergencia,
    sync: EstadoSincronizacionBonita,
    mensaje: str,
    ahora: datetime,
) -> None:
    """Conserva la emergencia y registra un error seguro para el reintento."""

    emergencia.bonita_sync = sync
    emergencia.bonita_ultimo_error = mensaje
    emergencia.bonita_ultimo_intento_en = ahora
    session.commit()
    session.refresh(emergencia)
