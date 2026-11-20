"""Cruza hechos confirmados de Bonita con necesidades y organizaciones locales."""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Convocatoria,
    ConvocatoriaLote,
    EstadoEmergencia,
    GravedadEmergencia,
    HechoMonitoreo,
    Lote,
    Organizacion,
)
from app.schemas.metricas import FiltrosMetricas
from app.schemas.monitoreo import (
    AdjudicacionConfirmada,
    CasoReiterado,
    CoberturaCierres,
    DecisionConvocatoria,
    DemandaRubro,
    FinalizacionOng,
    IndicadoresProceso,
    RankingOng,
    ResolucionEmergencia,
    ResolucionGravedad,
)
from app.services.filtros_metricas import emergencias_filtradas
from app.services.hechos_monitoreo import ADAPTADOR_HECHO

DEFINICIONES = [
    "Se seleccionan emergencias por fecha de alta; los hechos corresponden a toda su vida hasta la consulta. No representa eventos ocurridos exclusivamente dentro del período.",
    "Tasa de resolución = emergencias resueltas (estado local o cierre confirmado) / emergencias de la gravedad. Se informa cuántas resueltas carecen de evidencia de cierre. En término = cierres dentro del plazo / cierres con plazo explícito. Sin plazo, la tasa en término es null.",
    "Tiempo de resolución = resolución confirmada menos alerta informada. No se usa actualizada_en ni el vencimiento de ofertas como cierre o SLA.",
    "Reaperturas y reformulaciones cuentan decisiones confirmadas distintas por emergencia y ronda.",
    "Ranking separado por capacidad y unidad: cantidades adjudicadas por ONG. Cumplimiento = aportes finalizados dentro de plazo / aportes finalizados con plazo. Los pendientes se informan por separado.",
    "Cobertura total exige cumplir todos los lotes de la ronda de cierre; parcial incluye cualquier faltante. Proporciones sobre cierres con evidencia completa.",
    "Demanda = suma de necesidades publicadas por capacidad y unidad, incluyendo nuevas rondas.",
    "Alerta a adjudicación usa la primera adjudicación confirmada de cada emergencia. Las fechas de alerta son explícitas y los casos sin hechos no se sustituyen por ceros.",
]


def porcentaje(numerador: int, denominador: int) -> float | None:
    return 100 * numerador / denominador if denominador else None


@dataclass
class AcumuladoRanking:
    cantidad: Decimal = Decimal(0)
    aportes: int = 0
    finalizados: int = 0
    con_plazo: int = 0
    en_termino: int = 0


def obtener_indicadores(
    session: Session, filtros: FiltrosMetricas
) -> IndicadoresProceso:
    """Agrega evidencia persistida; todas las consultas usan la misma cohorte."""
    emergencias = session.scalars(emergencias_filtradas(filtros)).all()
    ids = [e.id for e in emergencias]
    hechos = [
        (h.emergencia_id, ADAPTADOR_HECHO.validate_python(h.datos))
        for h in session.scalars(
            select(HechoMonitoreo).where(HechoMonitoreo.emergencia_id.in_(ids))
        )
    ]
    publicaciones = {
        (c.emergencia_id, c.numero, p.lote_id): (
            p,
            p.codigo_capacidad_publicada or l.tipo_necesidad,
            p.unidad_publicada.strip().casefold(),
        )
        for c, p, l in session.execute(
            select(Convocatoria, ConvocatoriaLote, Lote)
            .join(ConvocatoriaLote, ConvocatoriaLote.convocatoria_id == Convocatoria.id)
            .join(Lote, Lote.id == ConvocatoriaLote.lote_id)
            .where(Convocatoria.emergencia_id.in_(ids))
        )
    }
    cierres = {eid: h for eid, h in hechos if isinstance(h, ResolucionEmergencia)}
    finalizaciones = {
        (eid, h.adjudicacion_ref, h.ong_id): h
        for eid, h in hechos
        if isinstance(h, FinalizacionOng)
    }
    nombres = dict(session.execute(select(Organizacion.id, Organizacion.nombre)).all())
    resoluciones: list[ResolucionGravedad] = []
    for gravedad in GravedadEmergencia:
        seleccionadas = [e for e in emergencias if e.gravedad == gravedad]
        resueltas = [cierres[e.id] for e in seleccionadas if e.id in cierres]
        sin_cierre = sum(
            e.estado == EstadoEmergencia.RESUELTA and e.id not in cierres
            for e in seleccionadas
        )
        con_plazo = [h for h in resueltas if h.plazo_en is not None]
        en_termino = sum(
            h.ocurrido_en <= h.plazo_en for h in con_plazo if h.plazo_en is not None
        )
        duraciones = [(h.ocurrido_en - h.alerta_en).total_seconds() for h in resueltas]
        duraciones_en_termino = [
            (h.ocurrido_en - h.alerta_en).total_seconds()
            for h in con_plazo
            if h.plazo_en is not None and h.ocurrido_en <= h.plazo_en
        ]
        resoluciones.append(
            ResolucionGravedad(
                gravedad=gravedad,
                emergencias=len(seleccionadas),
                resueltas=len(resueltas) + sin_cierre,
                cierres_confirmados=len(resueltas),
                resueltas_sin_cierre=sin_cierre,
                con_plazo=len(con_plazo),
                en_termino=en_termino,
                tasa_resolucion=porcentaje(
                    len(resueltas) + sin_cierre, len(seleccionadas)
                ),
                tasa_en_termino=porcentaje(en_termino, len(con_plazo)),
                promedio_segundos=sum(duraciones) / len(duraciones)
                if duraciones
                else None,
                promedio_en_termino_segundos=sum(duraciones_en_termino)
                / len(duraciones_en_termino)
                if duraciones_en_termino
                else None,
            )
        )
    decisiones: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    ranking: dict[tuple[int, str, str], AcumuladoRanking] = defaultdict(
        AcumuladoRanking
    )
    demanda: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for p, capacidad, unidad in publicaciones.values():
        demanda[(capacidad, unidad)] += p.cantidad_publicada
    primeras: dict[int, AdjudicacionConfirmada] = {}
    for eid, h in hechos:
        if isinstance(h, DecisionConvocatoria):
            if h.decision in {"REABRIR", "REFORMULAR"}:
                decisiones[eid][0 if h.decision == "REABRIR" else 1] += 1
        elif isinstance(h, AdjudicacionConfirmada):
            if eid not in primeras or h.ocurrido_en < primeras[eid].ocurrido_en:
                primeras[eid] = h
            for a in h.aportes:
                _, capacidad, unidad = publicaciones[
                    (eid, h.convocatoria_numero, a.lote_id)
                ]
                fila = ranking[(a.ong_id, capacidad, unidad)]
                fila.cantidad += a.cantidad
                fila.aportes += 1
                finalizacion = finalizaciones.get((eid, h.adjudicacion_ref, a.ong_id))
                if finalizacion:
                    fila.finalizados += 1
                    if a.plazo_en:
                        fila.con_plazo += 1
                        fila.en_termino += finalizacion.ocurrido_en <= a.plazo_en
    totales = sum(
        all(
            c.cantidad
            >= publicaciones[(eid, h.convocatoria_numero, c.lote_id)][
                0
            ].cantidad_publicada
            for c in h.cobertura
        )
        for eid, h in cierres.items()
    )
    demoras = [(h.ocurrido_en - h.alerta_en).total_seconds() for h in primeras.values()]
    con_hechos = len({eid for eid, _ in hechos})
    return IndicadoresProceso(
        emergencias_con_hechos=con_hechos,
        emergencias_sin_hechos=len(ids) - con_hechos,
        resolucion_por_gravedad=resoluciones,
        reiteradas=[
            CasoReiterado(emergencia_id=eid, reaperturas=v[0], reformulaciones=v[1])
            for eid, v in sorted(decisiones.items())
        ],
        ranking_ongs=[
            RankingOng(
                ong_id=ong_id,
                ong=nombres[ong_id],
                capacidad=capacidad,
                unidad=unidad,
                cantidad=f.cantidad,
                aportes=f.aportes,
                finalizados=f.finalizados,
                con_plazo_finalizados=f.con_plazo,
                en_termino=f.en_termino,
                tasa_cumplimiento=porcentaje(f.en_termino, f.con_plazo),
            )
            for (ong_id, capacidad, unidad), f in sorted(
                ranking.items(),
                key=lambda par: (par[0][1], par[0][2], -par[1].cantidad, par[0][0]),
            )
        ],
        cobertura_cierres=CoberturaCierres(
            total=totales,
            parcial=len(cierres) - totales,
            proporcion_total=porcentaje(totales, len(cierres)),
            proporcion_parcial=porcentaje(len(cierres) - totales, len(cierres)),
        ),
        demanda_rubros=[
            DemandaRubro(capacidad=capacidad, unidad=unidad, cantidad=cantidad)
            for (capacidad, unidad), cantidad in sorted(
                demanda.items(), key=lambda par: (par[0][1], -par[1], par[0][0])
            )
        ],
        alerta_adjudicacion_promedio_segundos=sum(demoras) / len(demoras)
        if demoras
        else None,
        alerta_adjudicacion_muestras=len(demoras),
        definiciones=DEFINICIONES,
    )
