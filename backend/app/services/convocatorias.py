"""Caso de uso para publicar la convocatoria de una emergencia.

Esta función solo confirma la publicación local; la sincronización con la
tarea humana `Generar lotes de necesidades` de Bonita se hace aparte, desde
la ruta HTTP, con `app.services.publicacion_bonita.completar_generacion_lotes`
(mismo criterio que separa `registrar_emergencia` de
`vincular_emergencia_con_bonita`).
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import get_settings
from app.db.models import (
    Convocatoria,
    ConvocatoriaLote,
    Emergencia,
    EstadoConvocatoria,
    EstadoEmergencia,
    EstadoLote,
    Lote,
    Organizacion,
    TipoOrganizacion,
    Usuario,
)
from app.schemas.paginacion import SIN_PAGINACION, Paginacion
from app.services.auth import organizacion_vigente_de_tipo
from app.services.notificaciones import notificar_convocatoria_publicada

VENTANA_CIERRE_PROVISORIA = timedelta(hours=2)
"""Marcador temporal de `cierra_en` hasta que Bonita confirme la fecha real."""

ESTADOS_EMERGENCIA_PUBLICABLES = frozenset(
    {EstadoEmergencia.REGISTRADA, EstadoEmergencia.EN_COORDINACION}
)


class ConvocatoriaError(Exception):
    """Fallo de dominio al publicar una convocatoria con mensaje apto para la API."""


class EmergenciaNoEncontradaError(ConvocatoriaError):
    """La emergencia indicada no existe."""


class CentroNoAutorizadoError(ConvocatoriaError):
    """El coordinador no pertenece al centro asignado a la emergencia."""


class EstadoEmergenciaInvalidoError(ConvocatoriaError):
    """La emergencia no admite publicar una convocatoria en su estado actual."""


class SinLotesValidosError(ConvocatoriaError):
    """La emergencia no tiene ningún lote en borrador para publicar."""


class DatosConvocatoriaInvalidosError(ConvocatoriaError):
    """La base rechazó la convocatoria aunque los datos previos parecían válidos."""


def publicar_convocatoria(
    session: Session,
    usuario: Usuario,
    emergencia_id: int,
) -> Convocatoria:
    """Publica la convocatoria de una emergencia con sus lotes en borrador.

    Crea la convocatoria, snapshotea los lotes en borrador como
    `ConvocatoriaLote`, los pasa a `PUBLICADO` y transiciona la emergencia a
    `PUBLICADA`, todo en una única transacción.

    Si la emergencia ya está `PUBLICADA` y conserva una convocatoria
    `ABIERTA`, no crea nada nuevo: devuelve esa convocatoria tal cual, para
    que el llamador pueda reintentar solo la sincronización con Bonita.

    Args:
        session: Sesión SQLAlchemy con la que se confirma la transacción.
        usuario: Coordinador regional vigente cargado desde PostgreSQL.
        emergencia_id: Emergencia a publicar.

    Returns:
        La convocatoria recién publicada, o la ya abierta si se trata de un
        reintento.

    Raises:
        EmergenciaNoEncontradaError: Si la emergencia no existe.
        CentroNoAutorizadoError: Si el usuario no conserva un centro activo o
            no es el asignado a la emergencia.
        EstadoEmergenciaInvalidoError: Si la emergencia no admite publicación
            ni reintento en su estado actual (por ejemplo, ya se cerró la
            convocatoria).
        SinLotesValidosError: Si no hay ningún lote en borrador para publicar.
        DatosConvocatoriaInvalidosError: Si la base rechaza la operación.
    """

    centro = _obtener_centro(usuario)
    emergencia = session.scalar(
        select(Emergencia).where(Emergencia.id == emergencia_id).with_for_update()
    )
    if emergencia is None:
        raise EmergenciaNoEncontradaError("La emergencia no existe.")
    if emergencia.centro_coordinador_id != centro.id:
        raise CentroNoAutorizadoError(
            "Solo el centro coordinador asignado publica esta convocatoria."
        )
    if emergencia.estado is EstadoEmergencia.PUBLICADA:
        convocatoria_abierta = _convocatoria_abierta(session, emergencia.id)
        if convocatoria_abierta is not None:
            return convocatoria_abierta
        raise EstadoEmergenciaInvalidoError(
            "La emergencia ya está publicada y no tiene una convocatoria "
            "abierta para reintentar."
        )
    if emergencia.estado not in ESTADOS_EMERGENCIA_PUBLICABLES:
        raise EstadoEmergenciaInvalidoError(
            f"La emergencia está {emergencia.estado} y no admite publicación."
        )

    lotes_borrador = session.scalars(
        select(Lote)
        .where(Lote.emergencia_id == emergencia.id, Lote.estado == EstadoLote.BORRADOR)
        .with_for_update()
    ).all()
    if not lotes_borrador:
        raise SinLotesValidosError(
            "La emergencia no tiene lotes en borrador para publicar."
        )
    sistema_origen = get_settings().nacional_sistema_origen
    if sistema_origen and any(
        l.capacidad_nacional_id is None or l.codigo_capacidad is None
        for l in lotes_borrador
    ):
        raise SinLotesValidosError(
            "Completá las capacidades nacionales antes de publicar."
        )

    ahora = datetime.now(UTC)
    convocatoria = Convocatoria(
        emergencia_id=emergencia.id,
        numero=_siguiente_numero(session, emergencia.id),
        estado=EstadoConvocatoria.ABIERTA,
        publicada_en=ahora,
        cierra_en=ahora + VENTANA_CIERRE_PROVISORIA,
        sistema_origen_ref=sistema_origen,
        gravedad_publicada=emergencia.gravedad,
    )
    session.add(convocatoria)
    session.flush()

    for lote in lotes_borrador:
        session.add(
            ConvocatoriaLote(
                convocatoria_id=convocatoria.id,
                lote_id=lote.id,
                cantidad_publicada=lote.cantidad_requerida,
                unidad_publicada=lote.unidad,
                capacidad_nacional_id=lote.capacidad_nacional_id,
                codigo_capacidad_publicada=lote.codigo_capacidad,
                admite_fracciones_publicada=lote.admite_fracciones,
                riesgo_requerido_publicado=lote.riesgo_requerido or emergencia.gravedad,
            )
        )
        lote.estado = EstadoLote.PUBLICADO

    emergencia.estado = EstadoEmergencia.PUBLICADA

    try:
        notificar_convocatoria_publicada(
            session,
            convocatoria_id=convocatoria.id,
            emergencia_id=emergencia.id,
            municipio_id=emergencia.municipio_id,
            zona=emergencia.zona,
            descripcion=emergencia.descripcion,
        )
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise DatosConvocatoriaInvalidosError(
            "Los datos de la convocatoria no son válidos."
        ) from error
    session.refresh(convocatoria)
    return convocatoria


def listar_convocatorias_abiertas(
    session: Session,
    paginacion: Paginacion = SIN_PAGINACION,
) -> list[Convocatoria]:
    """Devuelve las convocatorias abiertas visibles para cualquier ONG activa.

    No filtra por organización: una convocatoria abierta es pública por
    definición y no expone datos de ninguna ONG. Incluye el detalle de sus
    lotes publicados en una sola consulta.
    """

    return list(
        session.scalars(
            select(Convocatoria)
            .where(
                Convocatoria.estado == EstadoConvocatoria.ABIERTA,
                Convocatoria.cierra_en > datetime.now(UTC),
            )
            .options(
                selectinload(Convocatoria.lotes).selectinload(ConvocatoriaLote.lote),
                joinedload(Convocatoria.emergencia),
            )
            .order_by(Convocatoria.publicada_en.desc(), Convocatoria.id.desc())
            .offset(paginacion.offset)
            .limit(paginacion.limit)
        ).all()
    )


def _obtener_centro(usuario: Usuario) -> Organizacion:
    """Devuelve el centro activo del coordinador o rechaza la operación."""

    centro = organizacion_vigente_de_tipo(
        usuario,
        TipoOrganizacion.CENTRO_COORDINADOR,
    )
    if centro is None:
        raise CentroNoAutorizadoError(
            "Solo un centro coordinador activo publica convocatorias."
        )
    return centro


def _convocatoria_abierta(session: Session, emergencia_id: int) -> Convocatoria | None:
    """Busca, bloqueada, la convocatoria `ABIERTA` de la emergencia, si existe."""

    return session.scalar(
        select(Convocatoria)
        .where(
            Convocatoria.emergencia_id == emergencia_id,
            Convocatoria.estado == EstadoConvocatoria.ABIERTA,
        )
        .with_for_update()
    )


def _siguiente_numero(session: Session, emergencia_id: int) -> int:
    """Calcula el próximo número de convocatoria de la emergencia.

    Puede haber más de una convocatoria por emergencia a lo largo del
    tiempo (reapertura de una ronda), aunque esa lógica no es parte de T12.
    """

    ultimo = session.scalar(
        select(func.max(Convocatoria.numero)).where(
            Convocatoria.emergencia_id == emergencia_id
        )
    )
    return (ultimo or 0) + 1
