"""Resuelve el evento exacto del buzón y revalida permisos antes de mostrarlo."""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db.models import (
    Convocatoria,
    ConvocatoriaLote,
    Emergencia,
    Notificacion,
    Oferta,
    OfertaItem,
    OfertaVersion,
    RolUsuario,
    TipoNotificacion,
    TipoOrganizacion,
    Usuario,
)
from app.schemas.convocatoria import (
    ConvocatoriaAbiertaResponse,
    EmergenciaResumenResponse,
    LotePublicadoResponse,
)
from app.schemas.detalle_notificacion import (
    DetalleConvocatoriaResponse,
    DetalleNotificacionResponse,
    DetalleOfertaRecibidaResponse,
    DetalleTareaFallidaResponse,
    EmergenciaNotificadaResponse,
    ItemNotificadoResponse,
    OfertaNotificadaResponse,
)
from app.schemas.oferta import OfertaItemResponse, ParticipanteResponse
from app.services.auth import organizacion_vigente_de_tipo
from app.services.ofertas import listar_ofertas_propias


class DetalleNoDisponibleError(Exception):
    """El aviso o su entidad ya no están disponibles para el destinatario."""


class DetalleNoAutorizadoError(Exception):
    """El destinatario ya no conserva el rol o la organización necesarios."""


def _emergencia(emergencia: Emergencia) -> EmergenciaNotificadaResponse:
    return EmergenciaNotificadaResponse.model_validate(emergencia)


def _oferta(
    oferta: Oferta, *, ultima_presentada: bool = True
) -> OfertaNotificadaResponse:
    """El centro ve lo presentado; una ONG ve su versión vigente sin anticipar aportes."""
    if not oferta.versiones:
        raise DetalleNoDisponibleError("La oferta no conserva una versión disponible.")
    presentadas = [v for v in oferta.versiones if v.presentada_en is not None]
    version = (
        max(presentadas or oferta.versiones, key=lambda v: v.numero)
        if ultima_presentada
        else next(v for v in oferta.versiones if v.numero == oferta.version_actual)
    )
    participantes = [
        ParticipanteResponse(
            ong_id=p.ong_id,
            nombre=p.nombre_ong,
            rol=p.rol,
            confirmada=p.confirmada_en is not None,
        )
        for p in version.participantes
    ]
    if not participantes:
        participantes = [
            ParticipanteResponse(
                ong_id=oferta.ong_creadora_id,
                nombre=oferta.ong_creadora.nombre,
                rol="LIDER",
                confirmada=True,
            )
        ]
    return OfertaNotificadaResponse(
        id=oferta.id,
        estado=oferta.estado,
        version=version.numero,
        presentada_en=version.presentada_en,
        observaciones=version.observaciones,
        participantes=participantes,
        items=[
            ItemNotificadoResponse(
                **OfertaItemResponse.model_validate(item).model_dump(),
                necesidad=item.convocatoria_lote.lote.tipo_necesidad,
            )
            for item in sorted(version.items, key=lambda item: item.id)
        ]
        if version.presentada_en is not None
        else [],
    )


def consultar_detalle(
    session: Session, usuario: Usuario, notificacion_id: int
) -> DetalleNotificacionResponse:
    """Consulta sin modificar el buzón ni ejecutar acciones en Bonita."""
    aviso = session.scalar(
        select(Notificacion).where(
            Notificacion.id == notificacion_id,
            Notificacion.usuario_id == usuario.id,
        )
    )
    if aviso is None:
        raise DetalleNoDisponibleError("La notificación no está disponible.")
    clave = aviso.clave_evento
    if aviso.tipo == TipoNotificacion.OFERTA_RECIBIDA:
        coincidencia = re.fullmatch(r"oferta:([1-9][0-9]*):recibida", clave)
        centro = organizacion_vigente_de_tipo(
            usuario, TipoOrganizacion.CENTRO_COORDINADOR
        )
        if usuario.rol != RolUsuario.COORDINADOR_REGIONAL or centro is None:
            raise DetalleNoAutorizadoError(
                "Solo el centro responsable consulta la oferta recibida."
            )
        oferta = session.scalar(
            select(Oferta)
            .where(Oferta.id == int(coincidencia[1]) if coincidencia else False)
            .options(
                joinedload(Oferta.convocatoria).joinedload(Convocatoria.emergencia),
                joinedload(Oferta.ong_creadora),
                selectinload(Oferta.versiones)
                .selectinload(OfertaVersion.items)
                .selectinload(OfertaItem.aportes),
                selectinload(Oferta.versiones).selectinload(
                    OfertaVersion.participantes
                ),
            )
        )
        if oferta is None:
            raise DetalleNoDisponibleError("La oferta del aviso no está disponible.")
        emergencia = oferta.convocatoria.emergencia
        if emergencia.centro_coordinador_id != centro.id:
            raise DetalleNoAutorizadoError(
                "La emergencia pertenece a otro centro coordinador."
            )
        if not any(v.presentada_en is not None for v in oferta.versiones):
            raise DetalleNoDisponibleError("La oferta todavía no fue presentada.")
        return DetalleOfertaRecibidaResponse(
            emergencia=_emergencia(emergencia),
            oferta=_oferta(oferta),
            convocatoria_numero=oferta.convocatoria.numero,
        )
    if aviso.tipo in {
        TipoNotificacion.CONVOCATORIA_PUBLICADA,
        TipoNotificacion.CONVOCATORIA_CERRADA,
    }:
        if (
            usuario.rol != RolUsuario.REPRESENTANTE_ONG
            or organizacion_vigente_de_tipo(usuario, TipoOrganizacion.ONG) is None
        ):
            raise DetalleNoAutorizadoError(
                "Solo una ONG activa consulta esta convocatoria."
            )
        coincidencia = re.fullmatch(
            r"convocatoria:([1-9][0-9]*):(publicada|cerrada)", clave
        )
        convocatoria = session.scalar(
            select(Convocatoria)
            .where(Convocatoria.id == int(coincidencia[1]) if coincidencia else False)
            .options(
                joinedload(Convocatoria.emergencia),
                selectinload(Convocatoria.lotes).joinedload(ConvocatoriaLote.lote),
            )
        )
        if convocatoria is None:
            raise DetalleNoDisponibleError(
                "La convocatoria del aviso no está disponible."
            )
        ofertas = listar_ofertas_propias(
            session, usuario, convocatoria_id=convocatoria.id
        )
        return DetalleConvocatoriaResponse(
            emergencia=_emergencia(convocatoria.emergencia),
            convocatoria=ConvocatoriaAbiertaResponse(
                id=convocatoria.id,
                emergencia_id=convocatoria.emergencia_id,
                numero=convocatoria.numero,
                estado=convocatoria.estado,
                publicada_en=convocatoria.publicada_en,
                cierra_en=convocatoria.cierra_en,
                emergencia=EmergenciaResumenResponse.model_validate(
                    convocatoria.emergencia
                ),
                requiere_desglose_nacional=bool(convocatoria.sistema_origen_ref),
                lotes=[
                    LotePublicadoResponse(
                        lote_id=l.lote_id,
                        tipo_necesidad=l.lote.tipo_necesidad,
                        descripcion=l.lote.descripcion,
                        cantidad_publicada=l.cantidad_publicada,
                        unidad_publicada=l.unidad_publicada,
                        capacidad_nacional_id=l.capacidad_nacional_id,
                        codigo_capacidad_publicada=l.codigo_capacidad_publicada,
                        riesgo_requerido_publicado=l.riesgo_requerido_publicado,
                    )
                    for l in sorted(convocatoria.lotes, key=lambda l: l.lote_id)
                ],
            ),
            mi_oferta=_oferta(ofertas[0], ultima_presentada=False) if ofertas else None,
        )
    if aviso.tipo == TipoNotificacion.TAREA_BONITA_FALLIDA:
        if usuario.rol != RolUsuario.AUDITOR_DIRECTIVO:
            raise DetalleNoAutorizadoError("Solo un auditor consulta este incidente.")
        coincidencia = re.fullmatch(r"bonita:tarea:([1-9][0-9]*):fallida", clave)
        emergencia = (
            session.get(Emergencia, aviso.emergencia_id)
            if aviso.emergencia_id
            else None
        )
        if not coincidencia or emergencia is None or not aviso.tarea_bonita_nombre:
            raise DetalleNoDisponibleError(
                "El contexto de este incidente ya no está disponible."
            )
        return DetalleTareaFallidaResponse(
            emergencia=_emergencia(emergencia),
            tarea_id=int(coincidencia[1]),
            nombre=aviso.tarea_bonita_nombre,
            observada_en=aviso.creada_en,
        )
    raise DetalleNoDisponibleError("Este aviso no tiene un detalle asociado.")
