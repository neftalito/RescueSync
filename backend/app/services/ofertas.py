"""Caso de uso para registrar una oferta básica sobre lotes publicados."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
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
    OfertaItemAporte,
    OfertaVersion,
    OfertaVersionParticipante,
    TipoOrganizacion,
    TipoParticipacion,
    Usuario,
)
from app.schemas.inventario import RecursoResponse
from app.schemas.oferta import (
    OfertaContenidoRequest,
    OfertaCreateRequest,
    OfertaItemRequest,
    OfertaUpdateRequest,
)
from app.schemas.paginacion import SIN_PAGINACION, Paginacion
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
    *,
    referencias: tuple[UUID | None, dict[UUID, RecursoResponse]] | None = None,
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
            or_(
                Oferta.ong_creadora_id == ong.id,
                select(OfertaVersionParticipante.oferta_version_id)
                .join(
                    OfertaVersion,
                    OfertaVersion.id == OfertaVersionParticipante.oferta_version_id,
                )
                .where(
                    OfertaVersion.oferta_id == Oferta.id,
                    OfertaVersion.numero == Oferta.version_actual,
                    OfertaVersionParticipante.ong_id == ong.id,
                )
                .correlate(Oferta)
                .exists(),
            ),
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
    recursos = _validar_referencias(
        session, usuario, datos, publicaciones_validadas, referencias
    )
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
        recursos=recursos,
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

    return recargar_oferta(session, oferta.id)


def actualizar_oferta(
    session: Session,
    usuario: Usuario,
    oferta_id: int,
    datos: OfertaUpdateRequest,
    *,
    referencias: tuple[UUID | None, dict[UUID, RecursoResponse]] | None = None,
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
    vigente = session.scalar(
        select(OfertaVersion).where(
            OfertaVersion.oferta_id == oferta.id,
            OfertaVersion.numero == oferta.version_actual,
        )
    )
    if vigente is not None and len(vigente.participantes) > 1:
        raise OfertaNoEditableError(
            "Desarmá el consorcio antes de editar los aportes individuales."
        )
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
    recursos = _validar_referencias(
        session, usuario, datos, publicaciones_validadas, referencias
    )
    siguiente_version = siguiente_numero_version(session, oferta.id)
    _agregar_version(
        session,
        oferta=oferta,
        usuario=usuario,
        datos=datos,
        publicaciones=publicaciones_validadas,
        numero=siguiente_version,
        recursos=recursos,
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

    return recargar_oferta(session, oferta_id)


def listar_ofertas_propias(
    session: Session,
    usuario: Usuario,
    paginacion: Paginacion = SIN_PAGINACION,
    *,
    convocatoria_id: int | None = None,
) -> list[Oferta]:
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
                or_(convocatoria_id is None, Oferta.convocatoria_id == convocatoria_id),
                or_(
                    Oferta.ong_creadora_id == ong.id,
                    select(OfertaVersionParticipante.oferta_version_id)
                    .where(
                        OfertaVersionParticipante.oferta_version_id == OfertaVersion.id,
                        OfertaVersionParticipante.ong_id == ong.id,
                    )
                    .correlate(OfertaVersion)
                    .exists(),
                ),
                Oferta.fusionada_en_oferta_id.is_(None),
                or_(
                    OfertaVersion.presentada_en.is_not(None),
                    and_(
                        Oferta.estado == EstadoOferta.BORRADOR,
                        OfertaVersion.requiere_desglose_nacional,
                    ),
                ),
            )
            .options(
                joinedload(Oferta.convocatoria).joinedload(Convocatoria.emergencia),
                selectinload(Oferta.versiones).selectinload(OfertaVersion.items),
                selectinload(Oferta.versiones)
                .selectinload(OfertaVersion.items)
                .selectinload(OfertaItem.aportes),
                selectinload(Oferta.versiones).selectinload(
                    OfertaVersion.participantes
                ),
            )
            .order_by(Oferta.creada_en.desc(), Oferta.id.desc())
            .offset(paginacion.offset)
            .limit(paginacion.limit)
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
    recursos: dict[UUID, RecursoResponse],
) -> None:
    """Persiste una revisión completa sin alterar las revisiones anteriores."""

    version = OfertaVersion(
        oferta_id=oferta.id,
        creada_por_usuario_id=usuario.id,
        numero=numero,
        observaciones=datos.observaciones,
        presentada_en=None,
        requiere_desglose_nacional=bool(oferta.convocatoria.sistema_origen_ref)
        or any(p.capacidad_nacional_id is not None for p in publicaciones),
    )
    session.add(version)
    session.flush()
    ong = usuario.organizacion
    assert ong is not None
    session.add(
        OfertaVersionParticipante(
            oferta_version_id=version.id,
            ong_id=ong.id,
            ong_nacional_id=ong.ong_nacional_id,
            nombre_ong=ong.nombre,
            rol=TipoParticipacion.LIDER,
            confirmada_en=datetime.now(UTC),
        )
    )
    session.flush()
    for item, publicacion in zip(datos.items, publicaciones, strict=True):
        persistido = OfertaItem(
            oferta_version_id=version.id,
            convocatoria_id=oferta.convocatoria_id,
            lote_id=item.lote_id,
            tipo=item.tipo,
            descripcion=item.descripcion,
            cantidad_ofrecida=item.cantidad_ofrecida,
            unidad=publicacion.unidad_publicada,
        )
        session.add(persistido)
        session.flush()
        for aporte in item.aportes:
            recurso = recursos[aporte.recurso_nacional_id]
            session.add(
                OfertaItemAporte(
                    oferta_item_id=persistido.id,
                    oferta_version_id=version.id,
                    ong_id=ong.id,
                    recurso_nacional_id=recurso.id,
                    capacidad_nacional_id=recurso.capacidad_id,
                    cantidad=aporte.cantidad,
                    unidad=recurso.unidad,
                )
            )
    session.flush()
    version.presentada_en = datetime.now(UTC)


def siguiente_numero_version(session: Session, oferta_id: int) -> int:
    """No reutiliza números de propuestas de consorcio que fueron desarmadas."""
    return (
        session.scalar(
            select(func.max(OfertaVersion.numero)).where(
                OfertaVersion.oferta_id == oferta_id
            )
        )
        or 0
    ) + 1


def _validar_referencias(
    session: Session,
    usuario: Usuario,
    datos: OfertaContenidoRequest,
    publicaciones: list[ConvocatoriaLote],
    referencias: tuple[UUID | None, dict[UUID, RecursoResponse]] | None,
) -> dict[UUID, RecursoResponse]:
    """Revalida el mapping local tras HTTP; las competencias y reservas son posteriores."""
    ong = usuario.organizacion
    assert ong is not None
    session.refresh(ong, with_for_update=True)
    if not ong.activa or ong.tipo != TipoOrganizacion.ONG:
        raise OngNoAutorizadaError("Tu ONG local ya no está activa.")
    ong_id, recursos = referencias or (None, {})
    if ong_id is not None and ong_id != ong.ong_nacional_id:
        raise DatosOfertaInvalidosError(
            "La vinculación nacional cambió. Volvé a conectar tu cuenta."
        )
    for item, publicacion in zip(datos.items, publicaciones, strict=True):
        if publicacion.capacidad_nacional_id is not None and (
            not item.aportes or ong.ong_nacional_id is None
        ):
            raise DatosOfertaInvalidosError(
                "El lote requiere recursos nacionales propios y desglose de cantidades."
            )
        for aporte in item.aportes:
            recurso = recursos.get(aporte.recurso_nacional_id)
            if (
                recurso is None
                or recurso.ong_id != ong.ong_nacional_id
                or not recurso.activo
            ):
                raise DatosOfertaInvalidosError(
                    "El recurso debe pertenecer a tu inventario nacional activo."
                )
            if (
                recurso.capacidad_id != publicacion.capacidad_nacional_id
                or recurso.unidad != publicacion.unidad_publicada
            ):
                raise DatosOfertaInvalidosError(
                    "La capacidad y unidad del recurso no coinciden con el lote."
                )
            if (
                not recurso.admite_fracciones
                and aporte.cantidad != aporte.cantidad.to_integral_value()
            ):
                raise DatosOfertaInvalidosError(
                    "Esta capacidad requiere cantidades enteras."
                )
    return recursos


def recargar_oferta(session: Session, oferta_id: int) -> Oferta:
    """Carga la oferta con su convocatoria y versiones para formar la respuesta."""

    oferta = session.scalar(
        select(Oferta)
        .options(
            selectinload(Oferta.convocatoria),
            selectinload(Oferta.versiones).selectinload(OfertaVersion.items),
            selectinload(Oferta.versiones)
            .selectinload(OfertaVersion.items)
            .selectinload(OfertaItem.aportes),
            selectinload(Oferta.versiones).selectinload(OfertaVersion.participantes),
        )
        .where(Oferta.id == oferta_id)
        .execution_options(populate_existing=True)
    )
    assert oferta is not None
    return oferta
