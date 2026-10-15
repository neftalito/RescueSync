"""Casos de uso para consultar, crear, editar y eliminar lotes de necesidades."""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    Emergencia,
    EstadoEmergencia,
    EstadoLote,
    Lote,
    Organizacion,
    RolUsuario,
    TipoOrganizacion,
    Usuario,
)
from app.schemas.inventario import CapacidadResponse
from app.schemas.lote import LoteItem
from app.services.auth import organizacion_vigente_de_tipo


class LoteError(Exception):
    """Fallo de dominio al guardar lotes con mensaje apto para la API."""


class EmergenciaNoEncontradaError(LoteError):
    """La emergencia indicada no existe."""


class CentroNoAutorizadoError(LoteError):
    """El coordinador no pertenece al centro asignado a la emergencia."""


class OngNoAutorizadaError(LoteError):
    """La ONG no está activa y no puede consultar lotes publicados."""


class LoteNoEncontradoError(LoteError):
    """El lote a editar no existe dentro de la emergencia."""


class LoteNoEditableError(LoteError):
    """Solo un lote en borrador admite edición destructiva."""


class EstadoEmergenciaInvalidoError(LoteError):
    """La emergencia ya no admite crear ni modificar borradores."""


class LoteDesactualizadoError(LoteError):
    """La edición partió de una versión anterior del lote."""


class DatosLoteInvalidosError(LoteError):
    """La base rechazó los lotes aunque Pydantic los haya aceptado."""


def guardar_lotes(
    session: Session,
    usuario: Usuario,
    emergencia_id: int,
    items: list[LoteItem],
    capacidades: dict[UUID, CapacidadResponse] | None = None,
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
        EstadoEmergenciaInvalidoError: Si la emergencia ya fue publicada o cerrada.
        LoteDesactualizadoError: Si otro usuario modificó antes un lote.
        DatosLoteInvalidosError: Si la base rechaza la operación.
    """

    centro = _obtener_centro(usuario)
    emergencia = session.scalar(
        select(Emergencia).where(Emergencia.id == emergencia_id).with_for_update()
    )
    if emergencia is None:
        raise EmergenciaNoEncontradaError("La emergencia no existe.")
    if emergencia.centro_coordinador_id not in (None, centro.id):
        raise CentroNoAutorizadoError(
            "Solo el centro coordinador asignado gestiona estos lotes."
        )
    if emergencia.estado not in {
        EstadoEmergencia.REGISTRADA,
        EstadoEmergencia.EN_COORDINACION,
    }:
        raise EstadoEmergenciaInvalidoError(
            "La emergencia ya no admite guardar lotes en borrador."
        )
    if emergencia.centro_coordinador_id is None:
        emergencia.centro_coordinador_id = centro.id

    editables = _lotes_bloqueados(session, [item.id for item in items if item.id])
    if get_settings().nacional_sistema_origen and any(
        item.capacidad_nacional_id is None for item in items
    ):
        raise DatosLoteInvalidosError("Elegí una capacidad nacional para cada lote.")
    resultado = [
        _crear_lote(session, usuario, emergencia, item)
        if item.id is None
        else _editar_lote(emergencia, editables, item)
        for item in items
    ]
    for lote, item in zip(resultado, items, strict=True):
        capacidad = (
            (capacidades or {}).get(item.capacidad_nacional_id)
            if item.capacidad_nacional_id
            else None
        )
        if item.capacidad_nacional_id is not None and capacidad is None:
            raise DatosLoteInvalidosError(
                "La capacidad nacional debe verificarse antes de guardar."
            )
        if capacidad is not None:
            lote.tipo_necesidad = capacidad.nombre
            lote.unidad = capacidad.unidad
        lote.capacidad_nacional_id = capacidad.id if capacidad else None
        lote.codigo_capacidad = capacidad.codigo if capacidad else None
        lote.admite_fracciones = capacidad.admite_fracciones if capacidad else None
        lote.riesgo_requerido = item.riesgo_requerido
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
    """Devuelve los lotes de la emergencia según quién consulta.

    El centro coordinador asignado ve todos los lotes, en borrador o
    publicados, para retomar su edición; una ONG activa solo ve los lotes ya
    publicados, sin importar qué centro los gestiona. Consultar no reclama la
    emergencia: una emergencia sin centro asignado todavía no tiene lotes y
    el coordinador recibe una lista vacía.

    Raises:
        CentroNoAutorizadoError: Si el coordinador no conserva un centro
            activo o la emergencia está asignada a otro centro.
        OngNoAutorizadaError: Si la ONG no conserva una organización activa.
        EmergenciaNoEncontradaError: Si la emergencia no existe.
    """

    emergencia = session.get(Emergencia, emergencia_id)
    if emergencia is None:
        raise EmergenciaNoEncontradaError("La emergencia no existe.")

    if usuario.rol is RolUsuario.REPRESENTANTE_ONG:
        _obtener_ong(usuario)
        return list(
            session.scalars(
                select(Lote)
                .where(
                    Lote.emergencia_id == emergencia.id,
                    Lote.estado == EstadoLote.PUBLICADO,
                )
                .order_by(Lote.id)
            ).all()
        )

    centro = _obtener_centro(usuario)
    if emergencia.centro_coordinador_id is None:
        return []
    if emergencia.centro_coordinador_id != centro.id:
        raise CentroNoAutorizadoError(
            "Solo el centro coordinador asignado consulta estos lotes."
        )
    return list(
        session.scalars(
            select(Lote).where(Lote.emergencia_id == emergencia.id).order_by(Lote.id)
        ).all()
    )


def eliminar_lote(
    session: Session, usuario: Usuario, emergencia_id: int, lote_id: int
) -> None:
    """Elimina físicamente un lote en borrador de la emergencia.

    Un borrador nunca se publicó ni recibió ofertas, así que no deja rastro que
    conservar. Los lotes que salieron del borrador se rechazan, y la clave
    foránea `RESTRICT` de `convocatoria_lote` protege además a cualquier lote
    que haya llegado a una convocatoria.

    Raises:
        CentroNoAutorizadoError: Si el usuario no conserva un centro activo
            o la emergencia está asignada a otro centro.
        EmergenciaNoEncontradaError: Si la emergencia no existe.
        LoteNoEncontradoError: Si el lote no existe dentro de la emergencia.
        LoteNoEditableError: Si el lote ya salió del borrador.
    """

    centro = _obtener_centro(usuario)
    emergencia = session.scalar(
        select(Emergencia).where(Emergencia.id == emergencia_id).with_for_update()
    )
    if emergencia is None:
        raise EmergenciaNoEncontradaError("La emergencia no existe.")
    if emergencia.centro_coordinador_id not in (None, centro.id):
        raise CentroNoAutorizadoError(
            "Solo el centro coordinador asignado gestiona estos lotes."
        )

    lote = _lotes_bloqueados(session, [lote_id]).get(lote_id)
    if lote is None or lote.emergencia_id != emergencia.id:
        raise LoteNoEncontradoError(
            f"El lote {lote_id} no pertenece a esta emergencia."
        )
    if lote.estado is not EstadoLote.BORRADOR:
        raise LoteNoEditableError(
            f"El lote {lote_id} está {lote.estado} y ya no puede eliminarse."
        )

    # DELETE directo: `session.delete()` intentaría anular `lote_id` en
    # `convocatoria_lote`, que es parte de su clave primaria, antes de que
    # PostgreSQL aplique la restricción `RESTRICT`.
    try:
        session.execute(delete(Lote).where(Lote.id == lote.id))
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise LoteNoEditableError(
            f"El lote {lote_id} fue publicado en una convocatoria y no puede "
            "eliminarse."
        ) from error


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


def _obtener_ong(usuario: Usuario) -> Organizacion:
    """Devuelve la ONG activa del representante o rechaza la operación."""

    ong = organizacion_vigente_de_tipo(usuario, TipoOrganizacion.ONG)
    if ong is None:
        raise OngNoAutorizadaError("Solo una ONG activa consulta lotes publicados.")
    return ong


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
    assert item.version is not None
    if lote.version != item.version:
        raise LoteDesactualizadoError(
            f"El lote {item.id} cambió desde que lo consultaste. "
            "Recargá los lotes antes de volver a guardar."
        )
    lote.tipo_necesidad = item.tipo_necesidad
    lote.descripcion = item.descripcion
    lote.cantidad_requerida = item.cantidad_requerida
    lote.unidad = item.unidad
    lote.version += 1
    return lote
