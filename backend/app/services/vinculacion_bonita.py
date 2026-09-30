"""Vinculación trazable entre una emergencia local y su instancia en Bonita.

El alta confirma primero la emergencia en PostgreSQL y recién después inicia
el caso. La llamada HTTP nunca ocurre con una transacción de escritura
abierta: la vinculación se persiste en una transacción posterior. Un POST de
instanciación jamás se repite sin reconciliar antes con
`buscar_casos_por_emergencia`.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import Emergencia, EstadoSincronizacionBonita
from app.integrations.bonita.cliente import (
    BonitaResultadoDesconocidoError,
    ClienteBonita,
    ErrorBonita,
)
from app.integrations.bonita.contratos import ContratoInicioProceso

VIGENCIA_RECLAMO = timedelta(minutes=1)


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

    reclamo = _reclamar_intento(session, emergencia)
    if reclamo is None:
        return emergencia
    claim_id, requiere_reconciliacion, ahora = reclamo

    if requiere_reconciliacion:
        try:
            adoptada = _adoptar_caso_si_existe(
                session, emergencia, cliente, ahora, claim_id
            )
        except ErrorBonita as error:
            _persistir_estado(
                session,
                emergencia,
                EstadoSincronizacionBonita.RESULTADO_DESCONOCIDO,
                f"Reconciliación pendiente: {error}",
                ahora,
                claim_id,
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
        _resolver_incertidumbre(
            session, emergencia, cliente, str(error), ahora, claim_id
        )
        return emergencia
    except ErrorBonita as error:
        _persistir_estado(
            session,
            emergencia,
            EstadoSincronizacionBonita.ERROR,
            str(error),
            ahora,
            claim_id,
        )
        return emergencia

    _persistir_vinculo(
        session,
        emergencia,
        definicion.id,
        instancia.case_id,
        cliente.configuracion.version_proceso,
        ahora,
        claim_id,
    )
    return emergencia


def _reclamar_intento(
    session: Session,
    emergencia: Emergencia,
) -> tuple[str, bool, datetime] | None:
    """Serializa los reintentos y decide si antes debe reconciliar un POST."""

    ahora = datetime.now(UTC)
    bloqueada = session.scalar(
        select(Emergencia).where(Emergencia.id == emergencia.id).with_for_update()
    )
    if bloqueada is None:
        return None
    if (
        bloqueada.bonita_sync is EstadoSincronizacionBonita.VINCULADA
        and bloqueada.bonita_process_instance_id is not None
    ):
        session.commit()
        session.refresh(emergencia)
        return None

    reclamo_vigente = (
        bloqueada.bonita_claim_id is not None
        and bloqueada.bonita_ultimo_intento_en is not None
        and ahora - bloqueada.bonita_ultimo_intento_en < VIGENCIA_RECLAMO
    )
    if reclamo_vigente:
        session.commit()
        session.refresh(emergencia)
        return None

    requiere_reconciliacion = (
        bloqueada.bonita_sync is EstadoSincronizacionBonita.RESULTADO_DESCONOCIDO
        or bloqueada.bonita_claim_id is not None
    )
    claim_id = uuid4().hex
    bloqueada.bonita_claim_id = claim_id
    bloqueada.bonita_sync = EstadoSincronizacionBonita.PENDIENTE
    bloqueada.bonita_ultimo_error = None
    bloqueada.bonita_ultimo_intento_en = ahora
    session.commit()
    session.refresh(emergencia)
    return claim_id, requiere_reconciliacion, ahora


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
    claim_id: str,
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
        claim_id,
    )
    return True


def _resolver_incertidumbre(
    session: Session,
    emergencia: Emergencia,
    cliente: ClienteBonita,
    mensaje: str,
    ahora: datetime,
    claim_id: str,
) -> None:
    """Reconcilia un POST incierto antes de permitir cualquier reintento."""

    try:
        adoptada = _adoptar_caso_si_existe(
            session, emergencia, cliente, ahora, claim_id
        )
    except ErrorBonita as error:
        _persistir_estado(
            session,
            emergencia,
            EstadoSincronizacionBonita.RESULTADO_DESCONOCIDO,
            f"{mensaje} Reconciliación pendiente: {error}",
            ahora,
            claim_id,
        )
        return
    if not adoptada:
        _persistir_estado(
            session,
            emergencia,
            EstadoSincronizacionBonita.RESULTADO_DESCONOCIDO,
            mensaje,
            ahora,
            claim_id,
        )


def _persistir_vinculo(
    session: Session,
    emergencia: Emergencia,
    definicion_id: int,
    case_id: int,
    version_proceso: str,
    ahora: datetime,
    claim_id: str,
) -> None:
    """Guarda el `caseId` validado y marca la sincronización como vinculada."""

    session.execute(
        update(Emergencia)
        .where(
            Emergencia.id == emergencia.id,
            Emergencia.bonita_claim_id == claim_id,
        )
        .values(
            bonita_process_definition_id=definicion_id,
            bonita_process_instance_id=case_id,
            bonita_process_version=version_proceso,
            bonita_sync=EstadoSincronizacionBonita.VINCULADA,
            bonita_ultimo_error=None,
            bonita_ultimo_intento_en=ahora,
            bonita_claim_id=None,
        )
        .execution_options(synchronize_session=False)
    )
    session.commit()
    session.refresh(emergencia)


def _persistir_estado(
    session: Session,
    emergencia: Emergencia,
    sync: EstadoSincronizacionBonita,
    mensaje: str,
    ahora: datetime,
    claim_id: str,
) -> None:
    """Conserva la emergencia y registra un error seguro para el reintento."""

    session.execute(
        update(Emergencia)
        .where(
            Emergencia.id == emergencia.id,
            Emergencia.bonita_claim_id == claim_id,
        )
        .values(
            bonita_sync=sync,
            bonita_ultimo_error=mensaje,
            bonita_ultimo_intento_en=ahora,
            bonita_claim_id=None,
        )
        .execution_options(synchronize_session=False)
    )
    session.commit()
    session.refresh(emergencia)
