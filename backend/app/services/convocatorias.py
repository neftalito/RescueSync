"""Caso de uso para publicar la convocatoria de una emergencia.

La sincronización con la tarea humana `Generar lotes de necesidades` de
Bonita queda fuera de este caso de uso (ver ticket de seguimiento): esta
función solo confirma la publicación local. Mientras ese ticket no exista, el
proceso BPM queda detenido en esa tarea después de publicar aquí.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Convocatoria,
    ConvocatoriaLote,
    Emergencia,
    EstadoConvocatoria,
    EstadoEmergencia,
    EstadoLote,
    GravedadEmergencia,
    Lote,
    Organizacion,
    TipoOrganizacion,
    Usuario,
)
from app.services.auth import organizacion_vigente_de_tipo

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


@dataclass(frozen=True, slots=True)
class ConvocatoriaResumen:
    """Fila del listado de convocatorias de un centro coordinador.

    No expone la entidad ORM: el listado necesita el conteo de lotes publicados
    y los datos de la emergencia para que el coordinador identifique la
    convocatoria sin abrir cada emergencia.
    """

    id: int
    emergencia_id: int
    numero: int
    estado: EstadoConvocatoria
    publicada_en: datetime
    cierra_en: datetime
    cantidad_lotes: int
    gravedad: GravedadEmergencia
    zona: str


def publicar_convocatoria(
    session: Session,
    usuario: Usuario,
    emergencia_id: int,
) -> Convocatoria:
    """Publica la convocatoria de una emergencia con sus lotes en borrador.

    Crea la convocatoria, snapshotea los lotes en borrador como
    `ConvocatoriaLote`, los pasa a `PUBLICADO` y transiciona la emergencia a
    `PUBLICADA`, todo en una única transacción.

    Args:
        session: Sesión SQLAlchemy con la que se confirma la transacción.
        usuario: Coordinador regional vigente cargado desde PostgreSQL.
        emergencia_id: Emergencia a publicar.

    Returns:
        La convocatoria recién publicada.

    Raises:
        EmergenciaNoEncontradaError: Si la emergencia no existe.
        CentroNoAutorizadoError: Si el usuario no conserva un centro activo o
            no es el asignado a la emergencia.
        EstadoEmergenciaInvalidoError: Si la emergencia no admite publicación
            en su estado actual (por ejemplo, ya fue publicada).
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

    ahora = datetime.now(UTC)
    convocatoria = Convocatoria(
        emergencia_id=emergencia.id,
        numero=_siguiente_numero(session, emergencia.id),
        estado=EstadoConvocatoria.ABIERTA,
        publicada_en=ahora,
        cierra_en=ahora + VENTANA_CIERRE_PROVISORIA,
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
            )
        )
        lote.estado = EstadoLote.PUBLICADO

    emergencia.estado = EstadoEmergencia.PUBLICADA

    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise DatosConvocatoriaInvalidosError(
            "Los datos de la convocatoria no son válidos."
        ) from error
    session.refresh(convocatoria)
    return convocatoria


def listar_convocatorias(
    session: Session,
    usuario: Usuario,
    estado: EstadoConvocatoria | None = None,
) -> list[ConvocatoriaResumen]:
    """Devuelve las convocatorias de las emergencias del centro del coordinador.

    El filtro por `Emergencia.centro_coordinador_id` se resuelve en la base: el
    frontend solo ordena y filtra por estado, nunca decide qué puede ver.

    Args:
        session: Sesión SQLAlchemy de lectura.
        usuario: Coordinador regional vigente cargado desde PostgreSQL.
        estado: Si se informa, acota el resultado a ese estado.

    Returns:
        Las convocatorias del centro, de la más reciente a la más antigua.

    Raises:
        CentroNoAutorizadoError: Si el usuario no conserva un centro coordinador
            activo.
    """

    centro = _obtener_centro(usuario)
    consulta = (
        select(
            Convocatoria.id,
            Convocatoria.emergencia_id,
            Convocatoria.numero,
            Convocatoria.estado,
            Convocatoria.publicada_en,
            Convocatoria.cierra_en,
            func.count(ConvocatoriaLote.lote_id).label("cantidad_lotes"),
            Emergencia.gravedad,
            Emergencia.zona,
        )
        .join(Emergencia, Convocatoria.emergencia_id == Emergencia.id)
        .outerjoin(
            ConvocatoriaLote, ConvocatoriaLote.convocatoria_id == Convocatoria.id
        )
        .where(Emergencia.centro_coordinador_id == centro.id)
        .group_by(Convocatoria.id, Emergencia.gravedad, Emergencia.zona)
        .order_by(Convocatoria.publicada_en.desc(), Convocatoria.id.desc())
    )
    if estado is not None:
        consulta = consulta.where(Convocatoria.estado == estado)

    return [
        ConvocatoriaResumen(
            id=convocatoria_id,
            emergencia_id=emergencia_id,
            numero=numero,
            estado=estado_convocatoria,
            publicada_en=publicada_en,
            cierra_en=cierra_en,
            cantidad_lotes=cantidad_lotes,
            gravedad=gravedad,
            zona=zona,
        )
        for (
            convocatoria_id,
            emergencia_id,
            numero,
            estado_convocatoria,
            publicada_en,
            cierra_en,
            cantidad_lotes,
            gravedad,
            zona,
        ) in session.execute(consulta).all()
    ]


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


def _siguiente_numero(session: Session, emergencia_id: int) -> int:
    """Calcula el próximo número de convocatoria de la emergencia(pueden abrirse mas de una convocatoria por emergencia)"""

    ultimo = session.scalar(
        select(func.max(Convocatoria.numero)).where(
            Convocatoria.emergencia_id == emergencia_id
        )
    )
    return (ultimo or 0) + 1
