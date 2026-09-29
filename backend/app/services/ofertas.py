"""Caso de uso para registrar una oferta básica sobre lotes publicados."""

from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db.models import (
    Convocatoria,
    ConvocatoriaLote,
    EstadoConvocatoria,
    EstadoLote,
    EstadoOferta,
    Lote,
    Oferta,
    OfertaItem,
    OfertaVersion,
    TipoOrganizacion,
    Usuario,
)
from app.schemas.oferta import (
    OfertaContenidoRequest,
    OfertaCreateRequest,
    OfertaItemRequest,
    OfertaUpdateRequest,
)
from app.services.auth import organizacion_vigente_de_tipo
from app.services.notificaciones import notificar_oferta_recibida


class OfertaError(Exception):
    """Fallo de dominio al registrar una oferta con mensaje apto para la API."""


class OngNoAutorizadaError(OfertaError):
    """El usuario no representa a una ONG activa."""


class ConvocatoriaNoEncontradaError(OfertaError):
    """La convocatoria indicada no existe."""


class ConvocatoriaNoReceptivaError(OfertaError):
    """La convocatoria está cerrada, cancelada o fuera de ventana."""


class OfertaYaExisteError(OfertaError):
    """La ONG ya tiene una oferta estable para la convocatoria."""


class OfertaNoEncontradaError(OfertaError):
    """La oferta no existe o no pertenece a la ONG autenticada."""


class OfertaNoEditableError(OfertaError):
    """El estado actual de la oferta no permite modificarla."""


class VersionOfertaDesactualizadaError(OfertaError):
    """La oferta cambió desde que el usuario comenzó a editarla."""


class LoteNoOfertableError(OfertaError):
    """El lote no existe, no está publicado o es de otra convocatoria."""


class UnidadIncompatibleError(OfertaError):
    """La unidad ofrecida no coincide con la unidad publicada del lote."""


class CantidadOfrecidaExcedidaError(OfertaError):
    """La cantidad ofrecida supera la necesidad publicada del lote."""


class DatosOfertaInvalidosError(OfertaError):
    """La base rechazó la oferta aunque Pydantic la haya aceptado."""


def registrar_oferta(
    session: Session,
    usuario: Usuario,
    datos: OfertaCreateRequest,
) -> Oferta:
    """Persiste oferta, versión 1 e ítems en una única transacción."""

    ong = organizacion_vigente_de_tipo(usuario, TipoOrganizacion.ONG)
    if ong is None:
        raise OngNoAutorizadaError("Solo una ONG activa puede presentar ofertas.")

    convocatoria = session.scalar(
        select(Convocatoria)
        .where(Convocatoria.id == datos.convocatoria_id)
        .with_for_update()
    )
    if convocatoria is None:
        raise ConvocatoriaNoEncontradaError("La convocatoria no existe.")
    if (
        convocatoria.estado is not EstadoConvocatoria.ABIERTA
        or datetime.now(UTC) >= convocatoria.cierra_en
    ):
        raise ConvocatoriaNoReceptivaError("La convocatoria no admite nuevas ofertas.")

    oferta_existente_id = session.scalar(
        select(Oferta.id).where(
            Oferta.convocatoria_id == convocatoria.id,
            Oferta.ong_creadora_id == ong.id,
            Oferta.fusionada_en_oferta_id.is_(None),
        )
    )
    if oferta_existente_id is not None:
        raise OfertaYaExisteError(
            "La ONG ya presentó una oferta para esta convocatoria; puede editarla "
            "mientras la convocatoria permanezca abierta."
        )

    publicaciones = _publicaciones_bloqueadas(
        session, convocatoria.id, [item.lote_id for item in datos.items]
    )
    publicaciones_validadas = [
        _publicacion_de(publicaciones, item) for item in datos.items
    ]
    oferta = Oferta(
        convocatoria_id=convocatoria.id,
        ong_creadora_id=ong.id,
        creada_por_usuario_id=usuario.id,
        estado=EstadoOferta.PRESENTADA,
        version_actual=1,
        version_bloqueo=1,
    )
    session.add(oferta)
    session.flush()
    _agregar_version(
        session,
        oferta=oferta,
        usuario=usuario,
        datos=datos,
        publicaciones=publicaciones_validadas,
        numero=1,
    )

    try:
        emergencia = convocatoria.emergencia
        notificar_oferta_recibida(
            session,
            oferta_id=oferta.id,
            centro_coordinador_id=emergencia.centro_coordinador_id,
            zona=emergencia.zona,
        )
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise DatosOfertaInvalidosError(
            "Los datos de la oferta no son válidos."
        ) from error

    return _recargar_oferta(session, oferta.id)


def actualizar_oferta(
    session: Session,
    usuario: Usuario,
    oferta_id: int,
    datos: OfertaUpdateRequest,
) -> Oferta:
    """Agrega una versión inmutable a la oferta propia durante la convocatoria."""

    ong = organizacion_vigente_de_tipo(usuario, TipoOrganizacion.ONG)
    if ong is None:
        raise OngNoAutorizadaError("Solo una ONG activa puede modificar ofertas.")

    convocatoria_id = session.scalar(
        select(Oferta.convocatoria_id).where(
            Oferta.id == oferta_id,
            Oferta.ong_creadora_id == ong.id,
            Oferta.fusionada_en_oferta_id.is_(None),
        )
    )
    if convocatoria_id is None:
        raise OfertaNoEncontradaError("La oferta no existe.")

    convocatoria = session.scalar(
        select(Convocatoria).where(Convocatoria.id == convocatoria_id).with_for_update()
    )
    assert convocatoria is not None
    if (
        convocatoria.estado is not EstadoConvocatoria.ABIERTA
        or datetime.now(UTC) >= convocatoria.cierra_en
    ):
        raise ConvocatoriaNoReceptivaError(
            "La convocatoria cerró y la oferta ya no puede modificarse."
        )

    oferta = session.scalar(
        select(Oferta)
        .where(
            Oferta.id == oferta_id,
            Oferta.ong_creadora_id == ong.id,
            Oferta.fusionada_en_oferta_id.is_(None),
        )
        .with_for_update()
    )
    assert oferta is not None
    if oferta.estado is not EstadoOferta.PRESENTADA:
        raise OfertaNoEditableError(
            f"La oferta está {oferta.estado.value} y no admite modificaciones."
        )
    if oferta.version_bloqueo != datos.version_bloqueo:
        raise VersionOfertaDesactualizadaError(
            "La oferta fue modificada por otra sesión. Recargá los datos e intentá "
            "nuevamente."
        )

    publicaciones = _publicaciones_bloqueadas(
        session, convocatoria.id, [item.lote_id for item in datos.items]
    )
    publicaciones_validadas = [
        _publicacion_de(publicaciones, item) for item in datos.items
    ]
    siguiente_version = oferta.version_actual + 1
    _agregar_version(
        session,
        oferta=oferta,
        usuario=usuario,
        datos=datos,
        publicaciones=publicaciones_validadas,
        numero=siguiente_version,
    )
    oferta.version_actual = siguiente_version
    oferta.version_bloqueo += 1

    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise DatosOfertaInvalidosError(
            "Los datos de la oferta no son válidos."
        ) from error

    return _recargar_oferta(session, oferta_id)


def listar_ofertas_propias(session: Session, usuario: Usuario) -> list[Oferta]:
    """Devuelve las ofertas de la ONG activa del usuario, sin importar quién las creó.

    Nunca incluye ofertas de otra organización: la consulta filtra siempre
    por `ong_creadora_id` de la ONG vigente del usuario autenticado.

    Raises:
        OngNoAutorizadaError: Si el usuario no representa una ONG activa.
    """

    ong = organizacion_vigente_de_tipo(usuario, TipoOrganizacion.ONG)
    if ong is None:
        raise OngNoAutorizadaError("Solo una ONG activa consulta sus ofertas.")

    return list(
        session.scalars(
            select(Oferta)
            .join(
                OfertaVersion,
                and_(
                    OfertaVersion.oferta_id == Oferta.id,
                    OfertaVersion.numero == Oferta.version_actual,
                ),
            )
            .where(
                Oferta.ong_creadora_id == ong.id,
                Oferta.fusionada_en_oferta_id.is_(None),
                Oferta.estado != EstadoOferta.BORRADOR,
                OfertaVersion.presentada_en.is_not(None),
            )
            .options(
                joinedload(Oferta.convocatoria).joinedload(Convocatoria.emergencia),
                selectinload(Oferta.versiones).selectinload(OfertaVersion.items),
            )
            .order_by(Oferta.creada_en.desc())
        ).all()
    )


def _publicaciones_bloqueadas(
    session: Session, convocatoria_id: int, lote_ids: list[int]
) -> dict[int, ConvocatoriaLote]:
    filas = session.scalars(
        select(ConvocatoriaLote)
        .join(Lote, Lote.id == ConvocatoriaLote.lote_id)
        .where(
            ConvocatoriaLote.convocatoria_id == convocatoria_id,
            ConvocatoriaLote.lote_id.in_(lote_ids),
            Lote.estado == EstadoLote.PUBLICADO,
        )
        .with_for_update()
    ).all()
    return {fila.lote_id: fila for fila in filas}


def _publicacion_de(
    publicaciones: dict[int, ConvocatoriaLote], item: OfertaItemRequest
) -> ConvocatoriaLote:
    publicacion = publicaciones.get(item.lote_id)
    if publicacion is None:
        raise LoteNoOfertableError(
            f"El lote {item.lote_id} no está publicado en esta convocatoria."
        )
    if item.unidad != publicacion.unidad_publicada:
        raise UnidadIncompatibleError(
            f"La unidad del lote {item.lote_id} debe ser "
            f"{publicacion.unidad_publicada}."
        )
    if item.cantidad_ofrecida > publicacion.cantidad_publicada:
        raise CantidadOfrecidaExcedidaError(
            f"La cantidad ofrecida para el lote {item.lote_id} no puede superar "
            f"{publicacion.cantidad_publicada} {publicacion.unidad_publicada}."
        )
    return publicacion


def _agregar_version(
    session: Session,
    *,
    oferta: Oferta,
    usuario: Usuario,
    datos: OfertaContenidoRequest,
    publicaciones: list[ConvocatoriaLote],
    numero: int,
) -> None:
    """Persiste una revisión completa sin alterar las revisiones anteriores."""

    version = OfertaVersion(
        oferta_id=oferta.id,
        creada_por_usuario_id=usuario.id,
        numero=numero,
        observaciones=datos.observaciones,
        presentada_en=datetime.now(UTC),
    )
    session.add(version)
    session.flush()
    for item, publicacion in zip(datos.items, publicaciones, strict=True):
        session.add(
            OfertaItem(
                oferta_version_id=version.id,
                convocatoria_id=oferta.convocatoria_id,
                lote_id=item.lote_id,
                tipo=item.tipo,
                descripcion=item.descripcion,
                cantidad_ofrecida=item.cantidad_ofrecida,
                unidad=publicacion.unidad_publicada,
            )
        )


def _recargar_oferta(session: Session, oferta_id: int) -> Oferta:
    """Carga la oferta con su convocatoria y versiones para formar la respuesta."""

    oferta = session.scalar(
        select(Oferta)
        .options(
            selectinload(Oferta.convocatoria),
            selectinload(Oferta.versiones).selectinload(OfertaVersion.items),
        )
        .where(Oferta.id == oferta_id)
    )
    assert oferta is not None
    return oferta
