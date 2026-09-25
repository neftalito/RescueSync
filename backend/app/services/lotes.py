"""Casos de uso para consultar, crear y editar lotes de necesidades."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Emergencia,
    EstadoLote,
    Lote,
    Organizacion,
    TipoOrganizacion,
    Usuario,
)
from app.schemas.lote import LoteItem
from app.services.auth import organizacion_vigente_de_tipo


class LoteError(Exception):
    """Fallo de dominio al guardar lotes con mensaje apto para la API."""


class EmergenciaNoEncontradaError(LoteError):
    """La emergencia indicada no existe."""


class CentroNoAutorizadoError(LoteError):
    """El coordinador no pertenece al centro asignado a la emergencia."""


class LoteNoEncontradoError(LoteError):
    """El lote a editar no existe dentro de la emergencia."""


class LoteNoEditableError(LoteError):
    """Solo un lote en borrador admite edición destructiva."""


class DatosLoteInvalidosError(LoteError):
    """La base rechazó los lotes aunque Pydantic los haya aceptado."""


def guardar_lotes(
    session: Session,
    usuario: Usuario,
    emergencia_id: int,
    items: list[LoteItem],
) -> list[Lote]:
    """Crea o edita lotes en borrador dentro de una única transacción.

    Los ítems sin `id` se crean; los que traen `id` deben pertenecer a la
    emergencia y estar en borrador. Nunca crea convocatorias ni cambia el
    estado de la emergencia: guardar no publica.

    Args:
        session: Sesión SQLAlchemy con la que se confirma la transacción.
        usuario: Coordinador regional vigente cargado desde PostgreSQL.
        emergencia_id: Emergencia que contiene los lotes.
        items: Lotes a crear o editar ya validados por Pydantic.

    Returns:
        Los lotes persistidos en estado borrador.

    Raises:
        CentroNoAutorizadoError: Si el usuario no conserva un centro activo
            o no es el asignado a la emergencia.
        EmergenciaNoEncontradaError: Si la emergencia no existe.
        LoteNoEncontradoError: Si un lote a editar no es de la emergencia.
        LoteNoEditableError: Si un lote a editar ya salió del borrador.
        DatosLoteInvalidosError: Si la base rechaza la operación.
    """

    centro = _obtener_centro(usuario)
    emergencia = session.scalar(
        select(Emergencia).where(Emergencia.id == emergencia_id).with_for_update()
    )
    if emergencia is None:
        raise EmergenciaNoEncontradaError("La emergencia no existe.")
    if emergencia.centro_coordinador_id is None:
        emergencia.centro_coordinador_id = centro.id
    elif emergencia.centro_coordinador_id != centro.id:
        raise CentroNoAutorizadoError(
            "Solo el centro coordinador asignado gestiona estos lotes."
        )

    editables = _lotes_bloqueados(session, [item.id for item in items if item.id])
    resultado = [
        _crear_lote(session, usuario, emergencia, item)
        if item.id is None
        else _editar_lote(emergencia, editables, item)
        for item in items
    ]
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise DatosLoteInvalidosError(
            "Los datos de los lotes no son válidos."
        ) from error
    for lote in resultado:
        session.refresh(lote)
    return resultado


def listar_lotes(session: Session, usuario: Usuario, emergencia_id: int) -> list[Lote]:
    """Devuelve todos los lotes de la emergencia para que el coordinador los edite.

    Incluye borradores y lotes ya publicados, ordenados por alta; el estado
    indica cuáles admiten edición. Consultar no reclama la emergencia: una
    emergencia sin centro asignado todavía no tiene lotes y devuelve una lista
    vacía.

    Raises:
        CentroNoAutorizadoError: Si el usuario no conserva un centro activo
            o la emergencia está asignada a otro centro.
        EmergenciaNoEncontradaError: Si la emergencia no existe.
    """

    centro = _obtener_centro(usuario)
    emergencia = session.get(Emergencia, emergencia_id)
    if emergencia is None:
        raise EmergenciaNoEncontradaError("La emergencia no existe.")
    if emergencia.centro_coordinador_id not in (None, centro.id):
        raise CentroNoAutorizadoError(
            "Solo el centro coordinador asignado consulta estos lotes."
        )
    return list(
        session.scalars(
            select(Lote).where(Lote.emergencia_id == emergencia.id).order_by(Lote.id)
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
            "Solo un centro coordinador activo gestiona lotes."
        )
    return centro


def _lotes_bloqueados(session: Session, ids: list[int]) -> dict[int, Lote]:
    """Carga con bloqueo los lotes a editar para serializar escrituras."""

    if not ids:
        return {}
    lotes = session.scalars(
        select(Lote).where(Lote.id.in_(ids)).with_for_update()
    ).all()
    return {lote.id: lote for lote in lotes}


def _crear_lote(
    session: Session, usuario: Usuario, emergencia: Emergencia, item: LoteItem
) -> Lote:
    """Prepara un lote nuevo en borrador sin confirmar la transacción."""

    lote = Lote(
        emergencia_id=emergencia.id,
        creado_por_usuario_id=usuario.id,
        tipo_necesidad=item.tipo_necesidad,
        descripcion=item.descripcion,
        cantidad_requerida=item.cantidad_requerida,
        unidad=item.unidad,
        estado=EstadoLote.BORRADOR,
    )
    session.add(lote)
    return lote


def _editar_lote(
    emergencia: Emergencia, editables: dict[int, Lote], item: LoteItem
) -> Lote:
    """Aplica cambios a un lote en borrador ya bloqueado por la transacción."""

    assert item.id is not None
    lote = editables.get(item.id)
    if lote is None or lote.emergencia_id != emergencia.id:
        raise LoteNoEncontradoError(
            f"El lote {item.id} no pertenece a esta emergencia."
        )
    if lote.estado is not EstadoLote.BORRADOR:
        raise LoteNoEditableError(
            f"El lote {item.id} está {lote.estado} y ya no admite edición."
        )
    lote.tipo_necesidad = item.tipo_necesidad
    lote.descripcion = item.descripcion
    lote.cantidad_requerida = item.cantidad_requerida
    lote.unidad = item.unidad
    return lote
