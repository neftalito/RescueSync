"""Ofertas conjuntas a partir de aportes individuales, con consentimiento por versión."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Convocatoria,
    ConvocatoriaLote,
    EstadoConvocatoria,
    EstadoOferta,
    Oferta,
    OfertaItem,
    OfertaItemAporte,
    OfertaVersion,
    OfertaVersionParticipante,
    Organizacion,
    TipoOrganizacion,
    TipoParticipacion,
    Usuario,
)
from app.services.auth import organizacion_vigente_de_tipo
from app.services.ofertas import (
    DatosOfertaInvalidosError,
    OfertaNoEditableError,
    OfertaNoEncontradaError,
    VersionOfertaDesactualizadaError,
    recargar_oferta,
    siguiente_numero_version,
)


def _bloquear(
    session: Session, usuario: Usuario, oferta_id: int, bloqueo: int
) -> tuple[Oferta, OfertaVersion, int]:
    """Serializa cierre, invitación y aceptación mediante el mismo lock de ronda."""
    ong = organizacion_vigente_de_tipo(usuario, TipoOrganizacion.ONG)
    if ong is None:
        raise OfertaNoEncontradaError("La oferta no existe.")
    convocatoria_id = session.scalar(
        select(Oferta.convocatoria_id).where(Oferta.id == oferta_id)
    )
    convocatoria = session.scalar(
        select(Convocatoria).where(Convocatoria.id == convocatoria_id).with_for_update()
    )
    if (
        convocatoria is None
        or convocatoria.estado != EstadoConvocatoria.ABIERTA
        or datetime.now(UTC) >= convocatoria.cierra_en
    ):
        raise OfertaNoEditableError("La convocatoria no permite modificar consorcios.")
    oferta = session.scalar(
        select(Oferta)
        .where(Oferta.id == oferta_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert oferta is not None
    version = session.scalar(
        select(OfertaVersion)
        .where(
            OfertaVersion.oferta_id == oferta.id,
            OfertaVersion.numero == oferta.version_actual,
        )
        .execution_options(populate_existing=True)
    )
    if version is None or (
        oferta.ong_creadora_id != ong.id
        and all(p.ong_id != ong.id for p in version.participantes)
    ):
        raise OfertaNoEncontradaError("La oferta no existe.")
    if oferta.version_bloqueo != bloqueo:
        raise VersionOfertaDesactualizadaError(
            "La propuesta cambió. Actualizá el listado."
        )
    return oferta, version, ong.id


def proponer_consorcio(
    session: Session, usuario: Usuario, oferta_id: int, bloqueo: int, ong_ids: list[int]
) -> Oferta:
    """Congela versiones ya presentadas; una invitación no autoriza aportes ajenos."""
    oferta, original, ong_id = _bloquear(session, usuario, oferta_id, bloqueo)
    if (
        oferta.ong_creadora_id != ong_id
        or oferta.estado != EstadoOferta.PRESENTADA
        or len(original.participantes) != 1
        or not original.requiere_desglose_nacional
    ):
        raise OfertaNoEditableError(
            "La propuesta requiere tu oferta individual con recursos nacionales."
        )
    if ong_id in ong_ids:
        raise DatosOfertaInvalidosError("Tu ONG ya es líder de la propuesta.")
    fuentes = list(
        session.scalars(
            select(Oferta)
            .where(
                Oferta.convocatoria_id == oferta.convocatoria_id,
                Oferta.ong_creadora_id.in_(ong_ids),
                Oferta.fusionada_en_oferta_id.is_(None),
                Oferta.estado == EstadoOferta.PRESENTADA,
            )
            .order_by(Oferta.id)
            .with_for_update()
        )
    )
    if len(fuentes) != len(ong_ids):
        raise DatosOfertaInvalidosError(
            "Cada integrante necesita una oferta individual en la misma convocatoria."
        )
    versiones = [original]
    for fuente in fuentes:
        version = next(v for v in fuente.versiones if v.numero == fuente.version_actual)
        if not version.requiere_desglose_nacional or len(version.participantes) != 1:
            raise DatosOfertaInvalidosError(
                "Los integrantes deben tener aportes nacionales individuales."
            )
        versiones.append(version)
    propuesta = OfertaVersion(
        oferta_id=oferta.id,
        numero=siguiente_numero_version(session, oferta.id),
        creada_por_usuario_id=usuario.id,
        observaciones="Propuesta de consorcio: combinar las versiones individuales indicadas.",
        requiere_desglose_nacional=True,
    )
    session.add(propuesta)
    session.flush()
    for fuente in versiones:
        participante = fuente.participantes[0]
        session.add(
            OfertaVersionParticipante(
                oferta_version_id=propuesta.id,
                ong_id=participante.ong_id,
                ong_nacional_id=participante.ong_nacional_id,
                nombre_ong=participante.nombre_ong,
                rol=TipoParticipacion.LIDER
                if fuente.id == original.id
                else TipoParticipacion.MIEMBRO,
                confirmada_en=datetime.now(UTC) if fuente.id == original.id else None,
                version_origen_id=fuente.id,
            )
        )
    session.flush()
    por_lote: dict[int, OfertaItem] = {}
    publicaciones = {
        p.lote_id: p
        for p in session.scalars(
            select(ConvocatoriaLote).where(
                ConvocatoriaLote.convocatoria_id == oferta.convocatoria_id
            )
        )
    }
    for fuente in versiones:
        for item in fuente.items:
            combinado = por_lote.get(item.lote_id)
            if combinado is None:
                combinado = OfertaItem(
                    oferta_version_id=propuesta.id,
                    convocatoria_id=oferta.convocatoria_id,
                    lote_id=item.lote_id,
                    tipo=item.tipo,
                    descripcion="Aportes conjuntos de las ONGs participantes",
                    cantidad_ofrecida=item.cantidad_ofrecida,
                    unidad=item.unidad,
                )
                session.add(combinado)
                session.flush()
                por_lote[item.lote_id] = combinado
            else:
                combinado.cantidad_ofrecida += item.cantidad_ofrecida
            if (
                combinado.cantidad_ofrecida
                > publicaciones[item.lote_id].cantidad_publicada
            ):
                raise DatosOfertaInvalidosError(
                    "Los aportes conjuntos superan la necesidad publicada. Ajusten sus ofertas individuales."
                )
            for aporte in item.aportes:
                session.add(
                    OfertaItemAporte(
                        oferta_item_id=combinado.id,
                        oferta_version_id=propuesta.id,
                        ong_id=aporte.ong_id,
                        recurso_nacional_id=aporte.recurso_nacional_id,
                        capacidad_nacional_id=aporte.capacidad_nacional_id,
                        cantidad=aporte.cantidad,
                        unidad=aporte.unidad,
                    )
                )
    oferta.version_actual = propuesta.numero
    oferta.version_bloqueo += 1
    oferta.estado = EstadoOferta.BORRADOR
    session.commit()
    return recargar_oferta(session, oferta.id)


def confirmar_consorcio(
    session: Session, usuario: Usuario, oferta_id: int, bloqueo: int
) -> Oferta:
    """Sólo un integrante acepta su propio aporte; todos aceptan la misma propuesta."""
    oferta, version, ong_id = _bloquear(session, usuario, oferta_id, bloqueo)
    if oferta.estado != EstadoOferta.BORRADOR or len(version.participantes) < 2:
        raise OfertaNoEditableError("La oferta no tiene una propuesta pendiente.")
    participantes = list(version.participantes)
    fuentes: dict[int, OfertaVersion] = {}
    for participante in participantes:
        fuente = session.get(OfertaVersion, participante.version_origen_id)
        assert fuente is not None
        fuente_oferta = session.scalar(
            select(Oferta)
            .where(Oferta.id == fuente.oferta_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        assert fuente_oferta is not None
        if participante.rol == TipoParticipacion.MIEMBRO and (
            fuente_oferta.version_actual != fuente.numero
            or fuente_oferta.estado != EstadoOferta.PRESENTADA
            or fuente_oferta.fusionada_en_oferta_id is not None
        ):
            raise VersionOfertaDesactualizadaError(
                "Una oferta individual cambió. Desarmen la propuesta y creen otra."
            )
        actual = session.get(Organizacion, participante.ong_id, populate_existing=True)
        if (
            actual is None
            or not actual.activa
            or actual.ong_nacional_id != participante.ong_nacional_id
        ):
            raise DatosOfertaInvalidosError(
                "La vinculación de una participante cambió."
            )
        fuentes[participante.ong_id] = fuente
    participante = next(p for p in participantes if p.ong_id == ong_id)
    if participante.confirmada_en is None:
        participante.confirmada_en = datetime.now(UTC)
    if all(p.confirmada_en is not None for p in participantes):
        session.flush()
        version.presentada_en = datetime.now(UTC)
        oferta.estado = EstadoOferta.PRESENTADA
        for participante in participantes:
            if participante.rol == TipoParticipacion.MIEMBRO:
                fuentes[participante.ong_id].oferta.fusionada_en_oferta_id = oferta.id
    oferta.version_bloqueo += 1
    session.commit()
    return recargar_oferta(session, oferta.id)


def desarmar_consorcio(
    session: Session, usuario: Usuario, oferta_id: int, bloqueo: int
) -> Oferta:
    """Recupera las ofertas individuales sin borrar la propuesta ni sus snapshots."""
    oferta, version, _ = _bloquear(session, usuario, oferta_id, bloqueo)
    if (
        oferta.estado not in {EstadoOferta.BORRADOR, EstadoOferta.PRESENTADA}
        or len(version.participantes) < 2
    ):
        raise OfertaNoEditableError("La oferta no tiene un consorcio editable.")
    for participante in version.participantes:
        fuente = session.get(OfertaVersion, participante.version_origen_id)
        assert fuente is not None
        if participante.rol == TipoParticipacion.LIDER:
            oferta.version_actual = fuente.numero
        elif fuente.oferta.fusionada_en_oferta_id == oferta.id:
            fuente.oferta.fusionada_en_oferta_id = None
    oferta.estado = EstadoOferta.PRESENTADA
    oferta.version_bloqueo += 1
    session.commit()
    return recargar_oferta(session, oferta.id)
