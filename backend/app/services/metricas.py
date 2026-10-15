"""Agrega indicadores sin confundir ofrecimientos con recursos movilizados."""

from datetime import timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Convocatoria,
    ConvocatoriaLote,
    Emergencia,
    EstadoConvocatoria,
    EstadoEmergencia,
    EstadoOferta,
    GravedadEmergencia,
    Lote,
    Oferta,
    OfertaItem,
    OfertaVersion,
    OfertaVersionParticipante,
    Organizacion,
    TipoOrganizacion,
)
from app.schemas.metricas import (
    ZONA_REPORTES,
    CantidadOfrecida,
    ConteoMetrica,
    FiltrosMetricas,
    MunicipioMetrica,
    ReporteMetricas,
    ResumenMetricas,
)
from app.services.filtros_metricas import emergencias_filtradas
from app.services.indicadores_proceso import obtener_indicadores


def obtener_metricas(session: Session, filtros: FiltrosMetricas) -> ReporteMetricas:
    """Cuenta identidades estables y agrega solamente la versión vigente presentada."""
    ids = emergencias_filtradas(filtros).with_only_columns(Emergencia.id)
    estados = dict(
        session.execute(
            select(Emergencia.estado, func.count())
            .where(Emergencia.id.in_(ids))
            .group_by(Emergencia.estado)
        ).all()
    )
    gravedades = dict(
        session.execute(
            select(Emergencia.gravedad, func.count())
            .where(Emergencia.id.in_(ids))
            .group_by(Emergencia.gravedad)
        ).all()
    )
    mes = func.to_char(
        func.timezone(ZONA_REPORTES.key, Emergencia.creada_en), "YYYY-MM"
    )
    meses = dict(
        session.execute(
            select(mes, func.count()).where(Emergencia.id.in_(ids)).group_by(mes)
        ).all()
    )
    evolucion: list[ConteoMetrica] = []
    cursor = filtros.fecha_desde.replace(day=1)
    while cursor <= filtros.fecha_hasta:
        etiqueta = cursor.strftime("%Y-%m")
        evolucion.append(
            ConteoMetrica(categoria=etiqueta, cantidad=meses.get(etiqueta, 0))
        )
        if (cursor.year, cursor.month) == (
            filtros.fecha_hasta.year,
            filtros.fecha_hasta.month,
        ):
            break
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)

    # Una propuesta conjunta pendiente no reemplaza las ofertas individuales.
    participantes = (
        select(
            OfertaVersionParticipante.oferta_version_id.label("version_id"),
            func.count().label("cantidad"),
            func.bool_and(OfertaVersionParticipante.confirmada_en.is_not(None)).label(
                "confirmadas"
            ),
        )
        .group_by(OfertaVersionParticipante.oferta_version_id)
        .subquery()
    )
    versiones = (
        select(
            OfertaVersion.id.label("version_id"),
            func.coalesce(participantes.c.cantidad, 1).label("participantes"),
        )
        .join(
            Oferta,
            and_(
                Oferta.id == OfertaVersion.oferta_id,
                Oferta.version_actual == OfertaVersion.numero,
            ),
        )
        .join(Convocatoria, Convocatoria.id == Oferta.convocatoria_id)
        .outerjoin(participantes, participantes.c.version_id == OfertaVersion.id)
        .where(
            Convocatoria.emergencia_id.in_(ids),
            Oferta.fusionada_en_oferta_id.is_(None),
            Oferta.estado.not_in([EstadoOferta.BORRADOR, EstadoOferta.RETIRADA]),
            OfertaVersion.presentada_en.is_not(None),
            (func.coalesce(participantes.c.cantidad, 1) < 2)
            | participantes.c.confirmadas,
        )
        .subquery()
    )
    ids_versiones = select(versiones.c.version_id)
    es_conjunta = (versiones.c.participantes > 1).label("es_conjunta")
    ofertas = dict(
        session.execute(select(es_conjunta, func.count()).group_by("es_conjunta")).all()
    )
    # Las ofertas históricas anteriores al desglose guardan su ONG en la identidad.
    ongs = (
        select(OfertaVersionParticipante.ong_id)
        .where(OfertaVersionParticipante.oferta_version_id.in_(ids_versiones))
        .union(
            select(Oferta.ong_creadora_id)
            .join(OfertaVersion, OfertaVersion.oferta_id == Oferta.id)
            .where(OfertaVersion.id.in_(ids_versiones))
        )
    )
    cantidades = session.execute(
        select(
            func.coalesce(
                ConvocatoriaLote.codigo_capacidad_publicada, Lote.tipo_necesidad
            ).label("capacidad"),
            ConvocatoriaLote.codigo_capacidad_publicada,
            func.lower(func.trim(OfertaItem.unidad)).label("unidad"),
            func.sum(OfertaItem.cantidad_ofrecida),
        )
        .select_from(OfertaItem)
        .join(
            ConvocatoriaLote,
            and_(
                ConvocatoriaLote.convocatoria_id == OfertaItem.convocatoria_id,
                ConvocatoriaLote.lote_id == OfertaItem.lote_id,
            ),
        )
        .join(Lote, Lote.id == OfertaItem.lote_id)
        .where(OfertaItem.oferta_version_id.in_(ids_versiones))
        .group_by(
            func.coalesce(
                ConvocatoriaLote.codigo_capacidad_publicada, Lote.tipo_necesidad
            ),
            ConvocatoriaLote.codigo_capacidad_publicada,
            func.lower(func.trim(OfertaItem.unidad)),
        )
        .order_by("capacidad", "unidad")
    ).all()
    municipios = session.scalars(
        select(Organizacion)
        .where(Organizacion.tipo == TipoOrganizacion.MUNICIPIO)
        .order_by(Organizacion.nombre, Organizacion.id)
    ).all()
    total = sum(estados.values())
    return ReporteMetricas(
        indicadores_proceso=obtener_indicadores(session, filtros),
        filtros=filtros,
        municipios=[MunicipioMetrica(id=m.id, nombre=m.nombre) for m in municipios],
        resumen=ResumenMetricas(
            emergencias=total,
            activas=total
            - estados.get(EstadoEmergencia.RESUELTA, 0)
            - estados.get(EstadoEmergencia.CANCELADA, 0),
            resueltas=estados.get(EstadoEmergencia.RESUELTA, 0),
            convocatorias_abiertas=session.scalar(
                select(func.count())
                .select_from(Convocatoria)
                .where(
                    Convocatoria.emergencia_id.in_(ids),
                    Convocatoria.estado == EstadoConvocatoria.ABIERTA,
                )
            )
            or 0,
            ofertas_presentadas=sum(ofertas.values()),
            ong_participantes=session.scalar(
                select(func.count()).select_from(ongs.subquery())
            )
            or 0,
        ),
        por_estado=[
            ConteoMetrica(categoria=e.value, cantidad=estados.get(e, 0))
            for e in EstadoEmergencia
        ],
        por_gravedad=[
            ConteoMetrica(categoria=g.value, cantidad=gravedades.get(g, 0))
            for g in GravedadEmergencia
        ],
        evolucion_mensual=evolucion,
        tipos_oferta=[
            ConteoMetrica(categoria="INDIVIDUAL", cantidad=ofertas.get(False, 0)),
            ConteoMetrica(categoria="CONJUNTA", cantidad=ofertas.get(True, 0)),
        ],
        cantidades_ofrecidas=[
            CantidadOfrecida(
                capacidad=capacidad,
                codigo_capacidad=codigo,
                unidad=unidad,
                cantidad=cantidad,
            )
            for capacidad, codigo, unidad, cantidad in cantidades
        ],
    )
