"""Caso de uso para registrar una oferta básica sobre lotes publicados."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    Convocatoria,
    ConvocatoriaLote,
    EstadoConvocatoria,
    EstadoOferta,
    Oferta,
    OfertaItem,
    OfertaVersion,
    TipoOrganizacion,
    Usuario,
)
from app.schemas.oferta import OfertaCreateRequest, OfertaItemRequest
from app.services.auth import organizacion_vigente_de_tipo


class OfertaError(Exception):
    """Fallo de dominio al registrar una oferta con mensaje apto para la API."""


class OngNoAutorizadaError(OfertaError):
    """El usuario no representa a una ONG activa."""


class ConvocatoriaNoEncontradaError(OfertaError):
    """La convocatoria indicada no existe."""


class ConvocatoriaNoReceptivaError(OfertaError):
    """La convocatoria está cerrada, cancelada o fuera de ventana."""


class LoteNoOfertableError(OfertaError):
    """El lote no existe, no está publicado o es de otra convocatoria."""


class UnidadIncompatibleError(OfertaError):
    """La unidad ofrecida no coincide con la unidad publicada del lote."""


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
        raise ConvocatoriaNoReceptivaError(
            "La convocatoria no admite nuevas ofertas."
        )

    publicaciones = _publicaciones_bloqueadas(
        session, convocatoria.id, [item.lote_id for item in datos.items]
    )
    ahora = datetime.now(UTC)
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

    version = OfertaVersion(
        oferta_id=oferta.id,
        creada_por_usuario_id=usuario.id,
        numero=1,
        observaciones=datos.observaciones,
        presentada_en=ahora,
    )
    session.add(version)
    session.flush()

    for item in datos.items:
        publicacion = _publicacion_de(publicaciones, item)
        session.add(
            OfertaItem(
                oferta_version_id=version.id,
                convocatoria_id=convocatoria.id,
                lote_id=item.lote_id,
                tipo=item.tipo,
                descripcion=item.descripcion,
                cantidad_ofrecida=item.cantidad_ofrecida,
                unidad=publicacion.unidad_publicada,
            )
        )

    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise DatosOfertaInvalidosError(
            "Los datos de la oferta no son válidos."
        ) from error

    recargada = session.scalar(
        select(Oferta)
        .options(
            selectinload(Oferta.convocatoria),
            selectinload(Oferta.versiones).selectinload(OfertaVersion.items),
        )
        .where(Oferta.id == oferta.id)
    )
    assert recargada is not None
    return recargada


def _publicaciones_bloqueadas(
    session: Session, convocatoria_id: int, lote_ids: list[int]
) -> dict[int, ConvocatoriaLote]:
    filas = session.scalars(
        select(ConvocatoriaLote)
        .where(
            ConvocatoriaLote.convocatoria_id == convocatoria_id,
            ConvocatoriaLote.lote_id.in_(lote_ids),
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
    return publicacion
