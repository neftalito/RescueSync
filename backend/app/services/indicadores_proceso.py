"""Agrega las confirmaciones operativas y la evidencia histórica de monitoreo."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Convocatoria,
    ConvocatoriaLote,
    Emergencia,
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
    ResolucionConsorcios,
    ResolucionEmergencia,
    ResolucionGravedad,
    SuministrosMovilizados,
)
from app.services.filtros_metricas import emergencias_filtradas
from app.services.hechos_monitoreo import ADAPTADOR_HECHO
from app.services.monitoreo_ejecucion import AdjudicacionOperativa, obtener_ejecucion

DEFINICIONES = [
    "El período selecciona emergencias por fecha de alta. Sus resultados reflejan toda su vida hasta la consulta.",
    "Tasa de resolución = emergencias resueltas por estado local o cierre confirmado / emergencias de la gravedad.",
    "La alerta operativa comienza con el alta municipal. Una alerta explícita registrada para el caso conserva su fecha. Los tiempos usan la confirmación nacional de adjudicación o cierre.",
    "El porcentaje de resolución dentro del umbral compara el tiempo entre la alerta y el cierre confirmado con el límite del informe. Usa los cierres con duración verificable.",
    "Reaperturas y reformulaciones cuentan decisiones confirmadas por emergencia y ronda.",
    "El ranking agrupa cantidades adjudicadas por ONG, capacidad y unidad. Cada aporte corresponde a una ONG y un lote por adjudicación.",
    "El porcentaje de aportes dentro del umbral compara la duración entre la adjudicación confirmada y la finalización informada por la ONG. Usa aportes con liberación confirmada y duración verificable.",
    "Los umbrales se aplican a las duraciones transcurridas e incluyen el valor límite. Una semana equivale a 168 horas y un mes a 720 horas.",
    "La cobertura total exige que se cumplan todos los lotes de la ronda de cierre. Las proporciones usan cierres con evidencia completa de cantidades cumplidas.",
    "La demanda suma necesidades publicadas por capacidad y unidad, incluyendo nuevas rondas.",
    "Los suministros movilizados suman las cantidades declaradas por cada ONG al finalizar una participación liberada. Se informa la cantidad de participaciones con y sin registro.",
    "La resolución mediante consorcios cuenta cierres con al menos dos integrantes adjudicados de una misma oferta conjunta confirmada. El denominador son los cierres con adjudicación verificable.",
]

type Publicaciones = dict[tuple[int, int, int], tuple[ConvocatoriaLote, str, str]]
type CantidadesPorRubro = dict[tuple[str, str], Decimal]
type ClaveRanking = tuple[int, str, str]


def porcentaje(numerador: int, denominador: int) -> float | None:
    return 100 * numerador / denominador if denominador else None


def promedio(muestras: list[float]) -> float | None:
    return sum(muestras) / len(muestras) if muestras else None


def _duracion(inicio: datetime, fin: datetime) -> float | None:
    return (fin - inicio).total_seconds() if fin >= inicio else None


@dataclass
class AcumuladoRanking:
    cantidad: Decimal = Decimal(0)
    aportes: int = 0
    finalizados: int = 0
    finalizados_con_tiempo: int = 0
    dentro_del_umbral: int = 0

    def agregar(
        self,
        cantidad: Decimal,
        adjudicado_en: datetime,
        finalizado_en: datetime | None,
        umbral_segundos: int,
    ) -> None:
        self.cantidad += cantidad
        self.aportes += 1
        if finalizado_en is not None:
            self.finalizados += 1
            duracion = _duracion(adjudicado_en, finalizado_en)
            if duracion is not None:
                self.finalizados_con_tiempo += 1
                self.dentro_del_umbral += duracion <= umbral_segundos


@dataclass(frozen=True)
class CierreMonitoreado:
    ocurrido_en: datetime
    alerta_en: datetime
    cobertura_total: bool | None


def _cantidades_por_rubro(cantidades: CantidadesPorRubro) -> list[DemandaRubro]:
    return [
        DemandaRubro(capacidad=capacidad, unidad=unidad, cantidad=cantidad)
        for (capacidad, unidad), cantidad in sorted(
            cantidades.items(), key=lambda par: (par[0][1], -par[1], par[0][0])
        )
    ]


def _cobertura_operativa(
    adjudicacion: AdjudicacionOperativa, lotes: list[ConvocatoriaLote]
) -> bool | None:
    """Evalúa los lotes publicados solo cuando todas las ONG declararon cantidades."""
    if (
        not lotes
        or {ong for ong, _ in adjudicacion.cantidades}
        != adjudicacion.finalizaciones.keys()
    ):
        return None
    cumplidas: dict[int, Decimal] = defaultdict(Decimal)
    for finalizacion in adjudicacion.finalizaciones.values():
        if finalizacion.cantidades is None:
            return None
        for c in finalizacion.cantidades:
            cumplidas[c.lote_id] += c.cumplida
    return all(cumplidas[lote.lote_id] >= lote.cantidad_publicada for lote in lotes)


def _resoluciones_por_gravedad(
    emergencias: list[Emergencia],
    cierres: dict[int, CierreMonitoreado],
    umbral_segundos: int,
) -> list[ResolucionGravedad]:
    resoluciones: list[ResolucionGravedad] = []
    for gravedad in GravedadEmergencia:
        seleccionadas = [e for e in emergencias if e.gravedad == gravedad]
        resueltas = [cierres[e.id] for e in seleccionadas if e.id in cierres]
        sin_cierre = sum(
            e.estado == EstadoEmergencia.RESUELTA and e.id not in cierres
            for e in seleccionadas
        )
        duraciones = [
            segundos
            for h in resueltas
            if (segundos := _duracion(h.alerta_en, h.ocurrido_en)) is not None
        ]
        dentro_del_umbral = [
            segundos for segundos in duraciones if segundos <= umbral_segundos
        ]
        resoluciones.append(
            ResolucionGravedad(
                gravedad=gravedad,
                emergencias=len(seleccionadas),
                resueltas=len(resueltas) + sin_cierre,
                cierres_confirmados=len(resueltas),
                resueltas_sin_cierre=sin_cierre,
                cierres_con_tiempo=len(duraciones),
                dentro_del_umbral=len(dentro_del_umbral),
                tasa_resolucion=porcentaje(
                    len(resueltas) + sin_cierre, len(seleccionadas)
                ),
                tasa_dentro_del_umbral=porcentaje(
                    len(dentro_del_umbral), len(duraciones)
                ),
                promedio_segundos=promedio(duraciones),
                promedio_dentro_del_umbral_segundos=promedio(dentro_del_umbral),
            )
        )
    return resoluciones


def obtener_indicadores(
    session: Session, filtros: FiltrosMetricas
) -> IndicadoresProceso:
    """Cruza las fuentes por emergencia y ronda para evitar duplicar resultados."""
    umbral_aportes_segundos = filtros.umbral_aportes_horas * 3600
    emergencias = list(session.scalars(emergencias_filtradas(filtros)))
    alertas = {e.id: e.creada_en for e in emergencias}
    ids = list(alertas)
    hechos = [
        (h.emergencia_id, ADAPTADOR_HECHO.validate_python(h.datos))
        for h in session.scalars(
            select(HechoMonitoreo).where(HechoMonitoreo.emergencia_id.in_(ids))
        )
    ]
    con_hechos = {eid for eid, _ in hechos}
    publicaciones: Publicaciones = {
        (eid, ronda, p.lote_id): (
            p,
            p.codigo_capacidad_publicada or tipo,
            p.unidad_publicada.strip().casefold(),
        )
        for eid, ronda, p, tipo in session.execute(
            select(
                Convocatoria.emergencia_id,
                Convocatoria.numero,
                ConvocatoriaLote,
                Lote.tipo_necesidad,
            )
            .join(ConvocatoriaLote, ConvocatoriaLote.convocatoria_id == Convocatoria.id)
            .join(Lote, Lote.id == ConvocatoriaLote.lote_id)
            .where(Convocatoria.emergencia_id.in_(ids))
        )
    }
    demanda: CantidadesPorRubro = defaultdict(Decimal)
    publicados_por_ronda: dict[tuple[int, int], list[ConvocatoriaLote]] = defaultdict(
        list
    )
    for (eid, ronda, _), (p, capacidad, unidad) in publicaciones.items():
        demanda[capacidad, unidad] += p.cantidad_publicada
        publicados_por_ronda[eid, ronda].append(p)

    decisiones = {
        (eid, h.convocatoria_numero): h.decision
        for eid, h in hechos
        if isinstance(h, DecisionConvocatoria)
    }
    cierres: dict[int, CierreMonitoreado] = {}
    antiguas: dict[tuple[int, int], list[AdjudicacionConfirmada]] = defaultdict(list)
    finalizaciones = {
        (eid, h.adjudicacion_ref, h.ong_id): h.ocurrido_en
        for eid, h in hechos
        if isinstance(h, FinalizacionOng)
    }
    for eid, h in hechos:
        if isinstance(h, ResolucionEmergencia):
            alertas[eid] = h.alerta_en
            cierres[eid] = CierreMonitoreado(
                ocurrido_en=h.ocurrido_en,
                alerta_en=h.alerta_en,
                cobertura_total=all(
                    c.cantidad
                    >= publicaciones[eid, h.convocatoria_numero, c.lote_id][
                        0
                    ].cantidad_publicada
                    for c in h.cobertura
                ),
            )
        elif isinstance(h, AdjudicacionConfirmada):
            alertas[eid] = h.alerta_en
            antiguas[eid, h.convocatoria_numero].append(h)

    ejecucion = obtener_ejecucion(session, ids)
    decisiones.update(ejecucion.decisiones)
    con_hechos.update(eid for eid, _ in ejecucion.decisiones)
    con_hechos.update(ejecucion.cierres)
    con_hechos.update(a.emergencia_id for a in ejecucion.adjudicaciones)

    ranking: dict[ClaveRanking, AcumuladoRanking] = defaultdict(AcumuladoRanking)
    movilizadas: CantidadesPorRubro = defaultdict(Decimal)
    con_movilizacion = sin_movilizacion = 0
    primeras: dict[int, datetime] = {}
    for a in ejecucion.adjudicaciones:
        eid, ronda = a.emergencia_id, a.ronda
        primeras[eid] = min(primeras.get(eid, a.confirmada_en), a.confirmada_en)
        antiguas.pop((eid, ronda), None)
        for (ong, lote), cantidad in a.cantidades.items():
            _, capacidad, unidad = publicaciones[eid, ronda, lote]
            f = a.finalizaciones.get(ong)
            ranking[ong, capacidad, unidad].agregar(
                cantidad,
                a.confirmada_en,
                f.informada_en if f else None,
                umbral_aportes_segundos,
            )
        for f in a.finalizaciones.values():
            if f.cantidades is None:
                sin_movilizacion += 1
            else:
                con_movilizacion += 1
                for c in f.cantidades:
                    _, capacidad, unidad = publicaciones[eid, ronda, c.lote_id]
                    movilizadas[capacidad, unidad] += c.movilizada

    for (eid, ronda), adjudicaciones in antiguas.items():
        sin_participaciones: set[tuple[str, int]] = set()
        for h in adjudicaciones:
            primeras[eid] = min(primeras.get(eid, h.ocurrido_en), h.ocurrido_en)
            for a in h.aportes:
                _, capacidad, unidad = publicaciones[eid, ronda, a.lote_id]
                finalizado_en = finalizaciones.get((eid, h.adjudicacion_ref, a.ong_id))
                ranking[a.ong_id, capacidad, unidad].agregar(
                    a.cantidad, h.ocurrido_en, finalizado_en, umbral_aportes_segundos
                )
                if finalizado_en is not None:
                    sin_participaciones.add((h.adjudicacion_ref, a.ong_id))
        sin_movilizacion += len(sin_participaciones)

    for eid, c in ejecucion.cierres.items():
        anterior = cierres.get(eid)
        cobertura = _cobertura_operativa(
            c.adjudicacion, publicados_por_ronda[eid, c.adjudicacion.ronda]
        )
        cierres[eid] = CierreMonitoreado(
            ocurrido_en=c.cerrado_en,
            alerta_en=alertas[eid],
            cobertura_total=anterior.cobertura_total
            if cobertura is None and anterior
            else cobertura,
        )

    reiteradas: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for (eid, _), decision in decisiones.items():
        if decision in {"REABRIR", "REFORMULAR"}:
            reiteradas[eid][0 if decision == "REABRIR" else 1] += 1

    resoluciones = _resoluciones_por_gravedad(
        emergencias, cierres, filtros.umbral_resolucion_horas * 3600
    )
    resueltas = sum(r.resueltas for r in resoluciones)
    totales = sum(h.cobertura_total is True for h in cierres.values())
    parciales = sum(h.cobertura_total is False for h in cierres.values())
    por_consorcio = sum(
        c.adjudicacion.por_consorcio for c in ejecucion.cierres.values()
    )
    demoras = [
        (fecha - alertas[eid]).total_seconds()
        for eid, fecha in primeras.items()
        if fecha >= alertas[eid]
    ]
    nombres = dict(
        session.execute(
            select(Organizacion.id, Organizacion.nombre).where(
                Organizacion.id.in_({ong for ong, _, _ in ranking})
            )
        ).all()
    )
    return IndicadoresProceso(
        emergencias_con_hechos=len(con_hechos),
        emergencias_sin_hechos=len(ids) - len(con_hechos),
        resolucion_por_gravedad=resoluciones,
        reiteradas=[
            CasoReiterado(emergencia_id=eid, reaperturas=v[0], reformulaciones=v[1])
            for eid, v in sorted(reiteradas.items())
        ],
        ranking_ongs=[
            RankingOng(
                ong_id=ong,
                ong=nombres[ong],
                capacidad=capacidad,
                unidad=unidad,
                cantidad=f.cantidad,
                aportes=f.aportes,
                finalizados=f.finalizados,
                finalizados_con_tiempo=f.finalizados_con_tiempo,
                dentro_del_umbral=f.dentro_del_umbral,
                tasa_dentro_del_umbral=porcentaje(
                    f.dentro_del_umbral, f.finalizados_con_tiempo
                ),
            )
            for (ong, capacidad, unidad), f in sorted(
                ranking.items(),
                key=lambda par: (par[0][1], par[0][2], -par[1].cantidad, par[0][0]),
            )
        ],
        cobertura_cierres=CoberturaCierres(
            total=totales,
            parcial=parciales,
            proporcion_total=porcentaje(totales, totales + parciales),
            proporcion_parcial=porcentaje(parciales, totales + parciales),
            sin_evidencia=resueltas - totales - parciales,
        ),
        demanda_rubros=_cantidades_por_rubro(demanda),
        suministros_movilizados=SuministrosMovilizados(
            cantidades=_cantidades_por_rubro(movilizadas),
            participaciones_con_registro=con_movilizacion,
            participaciones_sin_registro=sin_movilizacion,
        ),
        resolucion_consorcios=ResolucionConsorcios(
            con_consorcio=por_consorcio,
            con_adjudicacion_verificable=len(ejecucion.cierres),
            sin_adjudicacion_verificable=resueltas - len(ejecucion.cierres),
            proporcion=porcentaje(por_consorcio, len(ejecucion.cierres)),
        ),
        alerta_adjudicacion_promedio_segundos=promedio(demoras),
        alerta_adjudicacion_muestras=len(demoras),
        definiciones=DEFINICIONES,
    )
